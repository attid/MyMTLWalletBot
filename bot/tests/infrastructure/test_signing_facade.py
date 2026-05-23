"""Tests for the signing facade contract."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.services.signing_facade import (
    SignatureMode,
    SignaturePurpose,
    SignatureRequest,
    SignatureStatus,
    SigningFacade,
)


@pytest.mark.asyncio
async def test_request_signature_stores_legacy_fsm_contract_and_prompts_user():
    """Facade stores legacy signing keys and starts the existing prompt flow."""
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    prompt_signature = AsyncMock()
    facade = SigningFacade(prompt_signature=prompt_signature)
    session = object()
    app_context = MagicMock()

    request = SignatureRequest(
        user_id=288101054,
        wallet_address="GA4CCEVTJALOO7T57DOLQLPLVE554CYS6CMIBHQJPS52QZOENXPH5ZSR",
        xdr="AAAA...",
        purpose=SignaturePurpose.SEP10_AUTH,
        mode=SignatureMode.SIGN_ONLY,
        operation="SEP-10 authentication",
        success_msg="Authenticated",
        correlation_id="anchor-transfer-1",
    )

    result = await facade.request_signature(
        session=session,
        state=state,
        request=request,
        app_context=app_context,
    )

    state.update_data.assert_awaited_once_with(
        xdr="AAAA...",
        operation="SEP-10 authentication",
        success_msg="Authenticated",
        fsm_after_send=None,
        signing_correlation_id="anchor-transfer-1",
        signing_purpose="sep10_auth",
    )
    prompt_signature.assert_awaited_once_with(
        session, 288101054, state, app_context=app_context
    )
    assert result.status is SignatureStatus.PENDING_USER
    assert result.correlation_id == "anchor-transfer-1"


@pytest.mark.asyncio
async def test_request_signature_sets_legacy_state_from_signature_mode():
    """Facade maps explicit signature modes to the legacy PIN states."""
    from routers.sign import PinState

    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    prompt_signature = AsyncMock()
    facade = SigningFacade(prompt_signature=prompt_signature)

    await facade.request_signature(
        session=object(),
        state=state,
        request=SignatureRequest(
            user_id=288101054,
            wallet_address="GA4CCEVTJALOO7T57DOLQLPLVE554CYS6CMIBHQJPS52QZOENXPH5ZSR",
            xdr="AAAA...",
            purpose=SignaturePurpose.SEP6_WITHDRAW_PAYMENT,
            mode=SignatureMode.SIGN_AND_SUBMIT,
            operation="SEP-6 withdraw payment",
        ),
        app_context=MagicMock(),
    )

    state.set_state.assert_awaited_once_with(PinState.sign_and_send)
