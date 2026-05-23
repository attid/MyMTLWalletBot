"""Tests for the signing facade contract."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.services.signing_facade import (
    PENDING_SIGNATURE_REQUEST_KEY,
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
        sign_msg="Signature request for anchor.example",
        prompt_msg="Enter PIN for SEP-10",
        success_msg="Authenticated",
        fsm_func='{"py/function": "sep10_after_sign"}',
        correlation_id="anchor-transfer-1",
        metadata={"asset_code": "BTCLN"},
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
        msg="Enter PIN for SEP-10",
        sign_msg="Signature request for anchor.example",
        success_msg="Authenticated",
        fsm_func='{"py/function": "sep10_after_sign"}',
        fsm_after_send=None,
        signing_correlation_id="anchor-transfer-1",
        signing_purpose="sep10_auth",
        signing_decode_enabled=True,
        signing_metadata={"asset_code": "BTCLN"},
        pin="",
        decode_tx_id=None,
        pending_signature_request=None,
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


@pytest.mark.asyncio
async def test_store_pending_signature_request_serializes_request_for_confirmation():
    """Confirmation screens store a serializable request, not loose XDR fields."""
    state = MagicMock()
    state.update_data = AsyncMock()
    facade = SigningFacade(prompt_signature=AsyncMock())

    request = SignatureRequest(
        user_id=288101054,
        wallet_address="GA4CCEVTJALOO7T57DOLQLPLVE554CYS6CMIBHQJPS52QZOENXPH5ZSR",
        xdr="AAAA...",
        purpose=SignaturePurpose.GENERIC,
        mode=SignatureMode.SIGN_AND_SUBMIT,
        operation="Send 10 XLM",
        sign_msg="Payment 10 XLM",
        success_msg="Sent",
        fsm_after_send='{"py/function": "after_send"}',
        correlation_id="send-1",
        metadata={"source": "send"},
    )

    await facade.store_pending_signature_request(state, request)

    state.update_data.assert_awaited_once()
    payload = state.update_data.await_args.kwargs[PENDING_SIGNATURE_REQUEST_KEY]
    assert payload["xdr"] == "AAAA..."
    assert payload["sign_msg"] == "Payment 10 XLM"
    assert payload["mode"] == "sign_and_submit"
    assert payload["metadata"] == {"source": "send"}


@pytest.mark.asyncio
async def test_request_pending_signature_loads_request_and_prompts_user():
    """Pending confirmation callback loads the request and starts the facade."""
    state = MagicMock()
    state.get_data = AsyncMock(
        return_value={
            PENDING_SIGNATURE_REQUEST_KEY: SignatureRequest(
                user_id=288101054,
                wallet_address="GA4CCEVTJALOO7T57DOLQLPLVE554CYS6CMIBHQJPS52QZOENXPH5ZSR",
                xdr="AAAA...",
                purpose=SignaturePurpose.GENERIC,
                mode=SignatureMode.SIGN_AND_SUBMIT,
                operation="Swap 10 XLM -> EURMTL",
                sign_msg="Swap 10 XLM -> EURMTL",
            ).to_state_data()
        }
    )
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    prompt_signature = AsyncMock()
    facade = SigningFacade(prompt_signature=prompt_signature)

    result = await facade.request_pending_signature(
        session=object(),
        state=state,
        app_context=MagicMock(),
    )

    assert result is not None
    assert result.status is SignatureStatus.PENDING_USER
    prompt_signature.assert_awaited_once()
    state.update_data.assert_awaited()
