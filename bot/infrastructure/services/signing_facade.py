"""Facade for requesting Stellar signatures without exposing router FSM details."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.services.app_context import AppContext


PENDING_SIGNATURE_REQUEST_KEY = "pending_signature_request"


class SignaturePurpose(str, Enum):
    """Business reason for a signature request."""

    GENERIC = "generic"
    PAYMENT = "payment"
    SWAP = "swap"
    SEP10_AUTH = "sep10_auth"
    SEP6_WITHDRAW_PAYMENT = "sep6_withdraw_payment"
    SEP24_TRANSFER_PAYMENT = "sep24_transfer_payment"
    CHEQUE = "cheque"
    TRADE = "trade"
    ASSET_TRUSTLINE = "asset_trustline"
    TOOLS = "tools"


class SignatureMode(str, Enum):
    """What should happen after the user signs the XDR."""

    SIGN_ONLY = "sign_only"
    SIGN_AND_SUBMIT = "sign_and_submit"


class SignatureStatus(str, Enum):
    """Immediate status returned after initiating a signature request."""

    PENDING_USER = "pending_user"
    # Rejected before the user was asked to sign (free-wallet policy, bad XDR).
    REJECTED = "rejected"


@dataclass(frozen=True)
class SignatureRequest:
    """Input contract for code that needs a user signature."""

    user_id: int
    wallet_address: str
    xdr: str
    purpose: SignaturePurpose = SignaturePurpose.GENERIC
    mode: SignatureMode = SignatureMode.SIGN_AND_SUBMIT
    operation: str = "Transaction"
    sign_msg: str | None = None
    prompt_msg: str | None = None
    success_msg: str | None = None
    fsm_func: str | None = None
    fsm_after_send: str | None = None
    correlation_id: str | None = None
    decode_enabled: bool = True
    metadata: dict[str, Any] | None = None

    def to_state_data(self) -> dict[str, Any]:
        """Serialize request into JSON-compatible FSM data."""
        return {
            "user_id": self.user_id,
            "wallet_address": self.wallet_address,
            "xdr": self.xdr,
            "purpose": self.purpose.value,
            "mode": self.mode.value,
            "operation": self.operation,
            "sign_msg": self.sign_msg,
            "prompt_msg": self.prompt_msg,
            "success_msg": self.success_msg,
            "fsm_func": self.fsm_func,
            "fsm_after_send": self.fsm_after_send,
            "correlation_id": self.correlation_id,
            "decode_enabled": self.decode_enabled,
            "metadata": self.metadata or {},
        }

    @classmethod
    def from_state_data(cls, data: dict[str, Any]) -> "SignatureRequest":
        """Restore a request serialized by `to_state_data`."""
        return cls(
            user_id=int(data["user_id"]),
            wallet_address=str(data["wallet_address"]),
            xdr=str(data["xdr"]),
            purpose=SignaturePurpose(data.get("purpose", SignaturePurpose.GENERIC)),
            mode=SignatureMode(data.get("mode", SignatureMode.SIGN_AND_SUBMIT)),
            operation=str(data.get("operation", "Transaction")),
            sign_msg=data.get("sign_msg"),
            prompt_msg=data.get("prompt_msg"),
            success_msg=data.get("success_msg"),
            fsm_func=data.get("fsm_func"),
            fsm_after_send=data.get("fsm_after_send"),
            correlation_id=data.get("correlation_id"),
            decode_enabled=bool(data.get("decode_enabled", True)),
            metadata=data.get("metadata") or {},
        )


@dataclass(frozen=True)
class SignatureResult:
    """Result of initiating a signature request."""

    status: SignatureStatus
    correlation_id: str | None = None


PromptSignature = Callable[
    [AsyncSession, int, FSMContext],
    Awaitable[None],
]


def _replace_xdr(request: SignatureRequest, xdr: str) -> SignatureRequest:
    """Copy a request with a (possibly rewritten) XDR."""
    if xdr == request.xdr:
        return request
    data = request.to_state_data()
    data["xdr"] = xdr
    return SignatureRequest.from_state_data(data)


class SigningFacade:
    """Starts legacy signing flow through an explicit request contract."""

    def __init__(self, prompt_signature: PromptSignature | None = None) -> None:
        self._prompt_signature = prompt_signature

    async def request_signature(
        self,
        *,
        session: AsyncSession,
        state: FSMContext,
        request: SignatureRequest,
        app_context: AppContext,
    ) -> SignatureResult:
        """Store the legacy FSM signing contract and prompt the user."""
        checked_xdr = await self._apply_free_wallet_policy(
            session=session,
            request=request,
            state=state,
            app_context=app_context,
        )
        if checked_xdr is None:
            return SignatureResult(
                status=SignatureStatus.REJECTED,
                correlation_id=request.correlation_id,
            )
        request = _replace_xdr(request, checked_xdr)

        await state.update_data(
            xdr=request.xdr,
            operation=request.operation,
            msg=request.prompt_msg,
            sign_msg=request.sign_msg,
            success_msg=request.success_msg,
            fsm_func=request.fsm_func,
            fsm_after_send=request.fsm_after_send,
            signing_correlation_id=request.correlation_id,
            signing_purpose=request.purpose.value,
            signing_decode_enabled=request.decode_enabled,
            signing_metadata=request.metadata or {},
            pin="",
            decode_tx_id=None,
            pending_signature_request=None,
        )
        await state.set_state(self._legacy_state_for_mode(request.mode))

        prompt_signature = self._prompt_signature or self._default_prompt_signature
        await prompt_signature(session, request.user_id, state, app_context=app_context)

        return SignatureResult(
            status=SignatureStatus.PENDING_USER,
            correlation_id=request.correlation_id,
        )

    async def store_pending_signature_request(
        self, state: FSMContext, request: SignatureRequest
    ) -> None:
        """Store a serializable request for a later confirmation callback."""
        await state.update_data(
            **{PENDING_SIGNATURE_REQUEST_KEY: request.to_state_data()}
        )

    async def request_pending_signature(
        self,
        *,
        session: AsyncSession,
        state: FSMContext,
        app_context: AppContext,
    ) -> SignatureResult | None:
        """Start signing from a request previously stored for confirmation."""
        data = await state.get_data()
        pending = data.get(PENDING_SIGNATURE_REQUEST_KEY)
        if not pending:
            return None
        request = SignatureRequest.from_state_data(pending)
        return await self.request_signature(
            session=session,
            state=state,
            request=request,
            app_context=app_context,
        )

    async def _apply_free_wallet_policy(
        self,
        *,
        session: AsyncSession,
        request: SignatureRequest,
        state: FSMContext,
        app_context: AppContext,
    ) -> str | None:
        """Return the XDR to sign, or None when the free-wallet policy rejects it.

        Every signature started through this facade (send, swap, trade, cheque,
        SEP-10 sign-only, WebApp publishing) must pass the policy from
        ADR-0003; it used to run only in `cmd_check_xdr`.
        """
        from other.stellar_tools import FreeWalletPolicyError
        from infrastructure.utils.telegram_utils import (
            clear_state,
            get_kb_return,
            my_gettext,
            send_message,
        )

        service = app_context.stellar_service
        try:
            is_free = await service.is_free_wallet(session, request.user_id)
        except Exception as exc:  # noqa: BLE001 - a lookup failure must not hide a payment
            logger.warning(
                f"signing_facade: free wallet lookup failed for "
                f"{request.user_id}: {exc}"
            )
            is_free = False

        if not is_free:
            return request.xdr

        free_wallet_public_key = request.wallet_address or None
        if not free_wallet_public_key:
            try:
                repo = app_context.repository_factory.get_wallet_repository(session)
                wallet = await repo.get_default_wallet(request.user_id)
                free_wallet_public_key = wallet.public_key if wallet else None
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"signing_facade: default wallet lookup failed for "
                    f"{request.user_id}: {exc}"
                )

        try:
            checked = await service.check_xdr(
                request.xdr,
                for_free_account=True,
                free_wallet_public_key=free_wallet_public_key,
            )
        except FreeWalletPolicyError as exc:
            logger.info(
                f"signing_facade: free-wallet policy rejected signature for "
                f"{request.user_id}: {exc}"
            )
            await clear_state(state)
            await send_message(
                session,
                request.user_id,
                my_gettext(
                    request.user_id, "bad_xdr_free_wallet", app_context=app_context
                ),
                reply_markup=get_kb_return(request.user_id, app_context=app_context),
                app_context=app_context,
            )
            return None

        # `check_xdr` returns None for payloads it cannot parse (e.g. an XDR of
        # another network); keep the original in that case so the downstream
        # flow reports it as before.
        return checked or request.xdr

    def _legacy_state_for_mode(self, mode: SignatureMode) -> Any:
        from routers.sign import PinState

        if mode is SignatureMode.SIGN_ONLY:
            return PinState.sign
        return PinState.sign_and_send

    async def _default_prompt_signature(
        self,
        session: AsyncSession,
        user_id: int,
        state: FSMContext,
        *,
        app_context: AppContext,
    ) -> None:
        from routers.sign import cmd_ask_pin

        await cmd_ask_pin(session, user_id, state, app_context=app_context)
