"""Facade for requesting Stellar signatures without exposing router FSM details."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.services.app_context import AppContext


class SignaturePurpose(str, Enum):
    """Business reason for a signature request."""

    GENERIC = "generic"
    SEP10_AUTH = "sep10_auth"
    SEP6_WITHDRAW_PAYMENT = "sep6_withdraw_payment"
    SEP24_TRANSFER_PAYMENT = "sep24_transfer_payment"


class SignatureMode(str, Enum):
    """What should happen after the user signs the XDR."""

    SIGN_ONLY = "sign_only"
    SIGN_AND_SUBMIT = "sign_and_submit"


class SignatureStatus(str, Enum):
    """Immediate status returned after initiating a signature request."""

    PENDING_USER = "pending_user"


@dataclass(frozen=True)
class SignatureRequest:
    """Input contract for code that needs a user signature."""

    user_id: int
    wallet_address: str
    xdr: str
    purpose: SignaturePurpose = SignaturePurpose.GENERIC
    mode: SignatureMode = SignatureMode.SIGN_AND_SUBMIT
    operation: str = "Transaction"
    success_msg: str | None = None
    fsm_after_send: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class SignatureResult:
    """Result of initiating a signature request."""

    status: SignatureStatus
    correlation_id: str | None = None


PromptSignature = Callable[
    [AsyncSession, int, FSMContext],
    Awaitable[None],
]


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
        await state.update_data(
            xdr=request.xdr,
            operation=request.operation,
            success_msg=request.success_msg,
            fsm_after_send=request.fsm_after_send,
            signing_correlation_id=request.correlation_id,
            signing_purpose=request.purpose.value,
        )
        await state.set_state(self._legacy_state_for_mode(request.mode))

        prompt_signature = self._prompt_signature or self._default_prompt_signature
        await prompt_signature(session, request.user_id, state, app_context=app_context)

        return SignatureResult(
            status=SignatureStatus.PENDING_USER,
            correlation_id=request.correlation_id,
        )

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
