"""Facade for SEP-10 authentication and SEP-24 transfers.

Protocol details live in `infrastructure/services/sep24/`; this module only
orchestrates them for the bot (which token to reuse, when to re-authenticate,
which core models to return).
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from loguru import logger
from stellar_sdk import Keypair, TransactionEnvelope

from core.models.anchor_asset import (
    AnchorAssetSupport,
    SepProtocol,
    SepProtocolSupport,
)
from core.models.anchor_transaction import (
    AnchorTransaction,
    AnchorTransactionProtocol,
)
from core.models.sep24 import (
    InteractiveSession,
    Sep10Challenge,
    Sep10Token,
    Sep24TransactionView,
)
from infrastructure.services.sep24 import (
    AnchorTransactionRequestError,
    Sep10ChallengeAccountMismatch,
    Sep10ChallengeInvalid,
    Sep10ChallengeRejected,
    Sep10TokenStore,
    Sep24Client,
    jwt_expires_at,
    parse_transaction_view,
    verify_sep10_challenge,
)

__all__ = [
    "AnchorTransactionRequestError",
    "AnchorTransactionService",
    "SEP10_VERIFICATION_FAILURES",
    "Sep24ReauthRequired",
]

# Observability for the soft (C2) verification: how often, and why, a live
# anchor's challenge failed verification.
SEP10_VERIFICATION_FAILURES: Counter[str] = Counter()

_ACCOUNT_MISMATCH_REASON = "account_mismatch"
_INVALID_CHALLENGE_REASON = "invalid_challenge"


class Sep24ReauthRequired(Exception):
    """The cached SEP-10 token is gone or rejected; the user must sign in again."""


T = TypeVar("T")


class AnchorTransactionService:
    def __init__(
        self,
        *,
        client: Sep24Client | None = None,
        token_store: Sep10TokenStore | None = None,
        fetch_json: Any = None,
        request_timeout: float = 5.0,
    ) -> None:
        if client is not None and fetch_json is not None:
            raise ValueError("pass either client or fetch_json, not both")
        self._client = client or Sep24Client(
            fetch_json=fetch_json,
            request_timeout=request_timeout,
        )
        self._token_store = token_store

    # ---------- SEP-10 ----------

    async def get_sep10_challenge_xdr(
        self, support: AnchorAssetSupport, account: str
    ) -> str:
        """Fetch and soft-verify the SEP-10 challenge for `account`."""
        challenge = await self._verified_challenge(support, account)
        return challenge.xdr

    async def exchange_sep10_token(
        self, web_auth_endpoint: str | None, signed_challenge_xdr: str
    ) -> str:
        token = await self._client.exchange_token(
            web_auth_endpoint, signed_challenge_xdr
        )
        return token.token

    async def remember_sep10_token(
        self,
        support: AnchorAssetSupport,
        token: str,
        *,
        user_id: int | None,
        public_key: str,
    ) -> None:
        """Cache a token obtained outside `authenticate` (WebApp signing path)."""
        if self._token_store is None or user_id is None or not token:
            return
        await self._token_store.set(
            user_id,
            public_key,
            support.anchor_domain,
            Sep10Token(token=token, expires_at=jwt_expires_at(token)),
        )

    async def authenticate(
        self,
        support: AnchorAssetSupport,
        keypair: Keypair,
        *,
        user_id: int | None = None,
    ) -> str | None:
        """Return a SEP-10 token, reusing the cached one when possible."""
        if not support.web_auth_endpoint:
            return None
        cached = await self._cached_token(support, keypair.public_key, user_id)
        if cached is not None:
            return cached.token
        token = await self._request_token(support, keypair)
        await self._store_token(support, keypair, user_id, token)
        return token.token

    # ---------- SEP-24 ----------

    async def start_sep24_interactive(
        self,
        support: AnchorAssetSupport,
        keypair: Keypair,
        *,
        operation: str,
        account: str | None = None,
        amount: str | None = None,
        lang: str | None = None,
        user_id: int | None = None,
    ) -> InteractiveSession:
        destination = account or keypair.public_key

        async def request(token: str | None) -> InteractiveSession:
            return await self._client.create_interactive(
                self._sep24_transfer_server(support),
                direction=operation,
                asset_code=support.asset_code_for(SepProtocol.SEP24),
                account=destination,
                amount=amount,
                lang=lang,
                token=token,
            )

        return await self._with_token(support, keypair, user_id, request)

    async def start_sep24_interactive_with_token(
        self,
        support: AnchorAssetSupport,
        token: str | None,
        *,
        operation: str,
        account: str,
        amount: str | None = None,
        lang: str | None = None,
    ) -> InteractiveSession:
        return await self._client.create_interactive(
            self._sep24_transfer_server(support),
            direction=operation,
            asset_code=support.asset_code_for(SepProtocol.SEP24),
            account=account,
            amount=amount,
            lang=lang,
            token=token,
        )

    async def fetch_sep24_transaction(
        self,
        support: AnchorAssetSupport,
        *,
        transaction_id: str,
        keypair: Keypair | None = None,
        token: str | None = None,
        user_id: int | None = None,
        lang: str | None = None,
    ) -> Sep24TransactionView:
        """Read one SEP-24 transaction (status, instructions, errors)."""

        async def request(auth_token: str | None) -> Sep24TransactionView:
            return await self._read_transaction(
                support, transaction_id=transaction_id, token=auth_token, lang=lang
            )

        if token is not None or keypair is None:
            return await request(token)
        return await self._with_token(support, keypair, user_id, request)

    async def fetch_sep24_transaction_cached(
        self,
        support: AnchorAssetSupport,
        *,
        transaction_id: str,
        user_id: int,
        public_key: str,
        lang: str | None = None,
    ) -> Sep24TransactionView:
        """Read a transaction using the cached token only (no PIN prompt)."""
        token = await self._cached_token(support, public_key, user_id)
        if token is None:
            raise Sep24ReauthRequired("no cached SEP-10 token")
        try:
            return await self._read_transaction(
                support, transaction_id=transaction_id, token=token.token, lang=lang
            )
        except AnchorTransactionRequestError as exc:
            if not exc.is_auth_error:
                raise
            await self._drop_token(support, public_key, user_id)
            raise Sep24ReauthRequired("anchor rejected the cached token") from exc

    async def _read_transaction(
        self,
        support: AnchorAssetSupport,
        *,
        transaction_id: str,
        token: str | None,
        lang: str | None,
    ) -> Sep24TransactionView:
        payload = await self._client.fetch_transaction(
            self._sep24_transfer_server(support),
            transaction_id=transaction_id,
            token=token,
            asset_code=support.asset_code_for(SepProtocol.SEP24),
            lang=lang,
        )
        return parse_transaction_view(
            payload,
            default_asset_code=support.asset_code_for(SepProtocol.SEP24),
            default_asset_issuer=support.asset.issuer,
        )

    # ---------- history ----------

    async def fetch_transactions(
        self,
        support: AnchorAssetSupport,
        keypair: Keypair,
        *,
        user_id: int | None = None,
    ) -> list[AnchorTransaction]:
        return await self._with_token(
            support,
            keypair,
            user_id,
            lambda token: self._fetch_transactions_with_token(support, token),
        )

    async def fetch_transactions_with_token(
        self, support: AnchorAssetSupport, token: str | None
    ) -> list[AnchorTransaction]:
        return await self._fetch_transactions_with_token(support, token)

    async def _fetch_transactions_with_token(
        self, support: AnchorAssetSupport, token: str | None
    ) -> list[AnchorTransaction]:
        jobs = [
            _fetch_protocol_transactions(
                self._client,
                protocol_support,
                protocol,
                support.asset_code_for(sep_protocol),
                token,
            )
            for protocol, protocol_support, sep_protocol in (
                (AnchorTransactionProtocol.SEP6, support.sep6, SepProtocol.SEP6),
                (AnchorTransactionProtocol.SEP24, support.sep24, SepProtocol.SEP24),
            )
            if protocol_support is not None
        ]
        transactions: list[AnchorTransaction] = []
        for result in await asyncio.gather(*jobs, return_exceptions=True):
            if isinstance(result, Exception):
                logger.info(f"SEP transactions request failed: {result}")
                continue
            transactions.extend(result)
        return transactions

    # ---------- internals ----------

    async def _with_token(
        self,
        support: AnchorAssetSupport,
        keypair: Keypair,
        user_id: int | None,
        action: Callable[[str | None], Awaitable[T]],
    ) -> T:
        """Run `action(token)`, re-authenticating once on a 401 response."""
        token = await self.authenticate(support, keypair, user_id=user_id)
        try:
            return await action(token)
        except AnchorTransactionRequestError as exc:
            if not exc.is_auth_error:
                raise
            logger.info(
                f"SEP auth token rejected by {support.anchor_domain}; re-authenticating"
            )
            await self._drop_token(support, keypair.public_key, user_id)
            refreshed = await self._request_token(support, keypair)
            await self._store_token(support, keypair, user_id, refreshed)
            return await action(refreshed.token)

    async def _verified_challenge(
        self, support: AnchorAssetSupport, account: str
    ) -> Sep10Challenge:
        challenge = await self._client.fetch_challenge(
            support.web_auth_endpoint,
            account=account,
            asset_code=self._challenge_asset_code(support),
        )
        self._check_challenge(support, challenge, account)
        return challenge

    def _check_challenge(
        self,
        support: AnchorAssetSupport,
        challenge: Sep10Challenge,
        account: str,
    ) -> None:
        try:
            verification = verify_sep10_challenge(
                challenge,
                account=account,
                anchor_domain=support.anchor_domain,
                web_auth_endpoint=support.web_auth_endpoint,
                signing_key=support.signing_key,
            )
        except (Sep10ChallengeAccountMismatch, Sep10ChallengeInvalid) as exc:
            reason = (
                _ACCOUNT_MISMATCH_REASON
                if isinstance(exc, Sep10ChallengeAccountMismatch)
                else _INVALID_CHALLENGE_REASON
            )
            SEP10_VERIFICATION_FAILURES[reason] += 1
            logger.warning(f"SEP-10 challenge rejected, not signing: {exc}")
            raise Sep10ChallengeRejected(str(exc)) from exc
        if verification.verified:
            logger.debug(f"SEP-10 challenge verified for {support.anchor_domain}")
            return
        SEP10_VERIFICATION_FAILURES[_short_reason(verification.reason)] += 1
        logger.warning(
            "SEP-10 challenge verification failed for "
            f"{support.anchor_domain}: {verification.reason}; signing anyway"
        )

    async def _request_token(
        self, support: AnchorAssetSupport, keypair: Keypair
    ) -> Sep10Token:
        challenge = await self._verified_challenge(support, keypair.public_key)
        envelope = TransactionEnvelope.from_xdr(
            challenge.xdr, challenge.network_passphrase
        )
        envelope.sign(keypair)
        return await self._client.exchange_token(
            support.web_auth_endpoint, envelope.to_xdr()
        )

    async def _cached_token(
        self,
        support: AnchorAssetSupport,
        public_key: str,
        user_id: int | None,
    ) -> Sep10Token | None:
        if self._token_store is None or user_id is None:
            return None
        return await self._token_store.get(user_id, public_key, support.anchor_domain)

    async def _store_token(
        self,
        support: AnchorAssetSupport,
        keypair: Keypair,
        user_id: int | None,
        token: Sep10Token,
    ) -> None:
        if self._token_store is None or user_id is None:
            return
        await self._token_store.set(
            user_id, keypair.public_key, support.anchor_domain, token
        )

    async def _drop_token(
        self,
        support: AnchorAssetSupport,
        public_key: str,
        user_id: int | None,
    ) -> None:
        if self._token_store is None or user_id is None:
            return
        await self._token_store.delete(user_id, public_key, support.anchor_domain)

    @staticmethod
    def _sep24_transfer_server(support: AnchorAssetSupport) -> str:
        if support.sep24 is None:
            raise ValueError("SEP-24 is not available for this asset")
        return support.sep24.transfer_server

    @staticmethod
    def _challenge_asset_code(support: AnchorAssetSupport) -> str | None:
        if support.sep24 is not None:
            return support.asset_code_for(SepProtocol.SEP24)
        if support.sep6 is not None:
            return support.asset_code_for(SepProtocol.SEP6)
        return None


async def _fetch_protocol_transactions(
    client: Sep24Client,
    protocol_support: SepProtocolSupport,
    protocol: AnchorTransactionProtocol,
    asset_code: str,
    token: str | None,
) -> list[AnchorTransaction]:
    response = await client.fetch_transactions(
        protocol_support.transfer_server,
        asset_code=asset_code,
        token=token,
    )
    raw_transactions = response.get("transactions", [])
    if not isinstance(raw_transactions, list):
        return []
    return [
        AnchorTransaction.from_raw(protocol, raw)
        for raw in raw_transactions
        if isinstance(raw, dict)
    ]


def _short_reason(reason: str | None) -> str:
    if not reason:
        return "unknown"
    return reason.strip().lower()[:60]
