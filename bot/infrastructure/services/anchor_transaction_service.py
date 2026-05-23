from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode
import asyncio

from loguru import logger
from stellar_sdk import Keypair, TransactionEnvelope

from core.models.anchor_asset import AnchorAssetSupport, SepProtocolSupport
from core.models.anchor_transaction import (
    AnchorTransaction,
    AnchorTransactionProtocol,
)
from other.web_tools import http_session_manager


FetchJson = Callable[
    [
        str,
        str,
        dict[str, Any] | None,
        dict[str, str] | None,
        dict[str, Any] | None,
    ],
    Awaitable[dict[str, Any]],
]


class AnchorTransactionService:
    def __init__(
        self,
        *,
        fetch_json: FetchJson | None = None,
        request_timeout: float = 5.0,
    ) -> None:
        self._fetch_json = fetch_json or self._default_fetch_json
        self._request_timeout = request_timeout

    async def fetch_transactions(
        self,
        support: AnchorAssetSupport,
        keypair: Keypair,
    ) -> list[AnchorTransaction]:
        token = await self._authenticate(support.web_auth_endpoint, keypair)
        return await self.fetch_transactions_with_token(support, token)

    async def fetch_transactions_with_token(
        self,
        support: AnchorAssetSupport,
        token: str | None,
    ) -> list[AnchorTransaction]:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        results = await asyncio.gather(
            self._fetch_protocol_transactions(
                AnchorTransactionProtocol.SEP6,
                support.sep6,
                support.asset.code,
                headers,
            ),
            self._fetch_protocol_transactions(
                AnchorTransactionProtocol.SEP24,
                support.sep24,
                support.asset.code,
                headers,
            ),
            return_exceptions=True,
        )
        transactions = []
        for result in results:
            if isinstance(result, Exception):
                logger.info(f"SEP transactions request failed: {result}")
                continue
            transactions.extend(result)
        return transactions

    async def start_sep24_interactive(
        self,
        support: AnchorAssetSupport,
        keypair: Keypair,
        *,
        operation: str,
    ) -> str:
        if support.sep24 is None:
            raise ValueError("SEP-24 is not available for this asset")
        if operation not in {"deposit", "withdraw"}:
            raise ValueError(f"Unsupported SEP-24 operation: {operation}")

        token = await self._authenticate(support.web_auth_endpoint, keypair)
        return await self.start_sep24_interactive_with_token(
            support,
            token,
            operation=operation,
        )

    async def start_sep24_interactive_with_token(
        self,
        support: AnchorAssetSupport,
        token: str | None,
        *,
        operation: str,
    ) -> str:
        if support.sep24 is None:
            raise ValueError("SEP-24 is not available for this asset")
        if operation not in {"deposit", "withdraw"}:
            raise ValueError(f"Unsupported SEP-24 operation: {operation}")

        headers = {"Authorization": f"Bearer {token}"} if token else None
        response = await self._fetch_json(
            "POST",
            (
                f"{support.sep24.transfer_server.rstrip('/')}/transactions/"
                f"{operation}/interactive"
            ),
            None,
            headers,
            {"asset_code": support.asset.code},
        )
        url = response.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("SEP-24 interactive response did not include url")
        return url

    async def get_sep10_challenge_xdr(
        self, web_auth_endpoint: str | None, account: str
    ) -> str:
        challenge_xdr, _ = await self._fetch_sep10_challenge(
            web_auth_endpoint,
            account,
        )
        return challenge_xdr

    async def exchange_sep10_token(
        self, web_auth_endpoint: str | None, signed_challenge_xdr: str
    ) -> str:
        if not web_auth_endpoint:
            raise ValueError("SEP-10 WEB_AUTH_ENDPOINT is not available")

        auth_response = await self._fetch_json(
            "POST",
            web_auth_endpoint,
            None,
            None,
            {"transaction": signed_challenge_xdr},
        )
        token = auth_response.get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("SEP-10 token response is invalid")
        return token

    async def _authenticate(
        self, web_auth_endpoint: str | None, keypair: Keypair
    ) -> str | None:
        if not web_auth_endpoint:
            return None

        challenge_xdr, network_passphrase = await self._fetch_sep10_challenge(
            web_auth_endpoint,
            keypair.public_key,
        )
        envelope = TransactionEnvelope.from_xdr(challenge_xdr, network_passphrase)
        envelope.sign(keypair)
        return await self.exchange_sep10_token(
            web_auth_endpoint,
            envelope.to_xdr(),
        )

    async def _fetch_sep10_challenge(
        self, web_auth_endpoint: str | None, account: str
    ) -> tuple[str, str]:
        if not web_auth_endpoint:
            raise ValueError("SEP-10 WEB_AUTH_ENDPOINT is not available")

        challenge = await self._fetch_json(
            "GET",
            web_auth_endpoint,
            {"account": account},
            None,
            None,
        )
        challenge_xdr = challenge.get("transaction")
        network_passphrase = challenge.get("network_passphrase")
        if not isinstance(challenge_xdr, str) or not isinstance(
            network_passphrase, str
        ):
            raise ValueError("SEP-10 challenge response is invalid")
        return challenge_xdr, network_passphrase

    async def _fetch_protocol_transactions(
        self,
        protocol: AnchorTransactionProtocol,
        protocol_support: SepProtocolSupport | None,
        asset_code: str,
        headers: dict[str, str] | None,
    ) -> list[AnchorTransaction]:
        if protocol_support is None:
            return []

        response = await self._fetch_json(
            "GET",
            f"{protocol_support.transfer_server.rstrip('/')}/transactions",
            {"asset_code": asset_code},
            headers,
            None,
        )
        raw_transactions = response.get("transactions", [])
        if not isinstance(raw_transactions, list):
            return []
        return [
            AnchorTransaction.from_raw(protocol, raw)
            for raw in raw_transactions
            if isinstance(raw, dict)
        ]

    async def _default_fetch_json(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if params:
            url = url + "?" + urlencode(params)
        response = await asyncio.wait_for(
            http_session_manager.get_web_request(
                method,
                url,
                headers=headers,
                data=data,
                return_type="json",
            ),
            timeout=self._request_timeout,
        )
        if response.status >= 400 or not isinstance(response.data, dict):
            raise AnchorTransactionRequestError(
                url=url,
                status=response.status,
                body=response.data,
            )
        return response.data


class AnchorTransactionRequestError(Exception):
    def __init__(self, *, url: str, status: int, body: object) -> None:
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"Unexpected JSON response from {url}: {status}; body={body}")
