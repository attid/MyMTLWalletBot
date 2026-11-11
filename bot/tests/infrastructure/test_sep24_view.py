from infrastructure.services.sep24.view import parse_transaction_view

MUXED = "MCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYKAAAAAAAAAA73IMRS"


def test_parses_wrapped_transaction_payload():
    payload = {
        "transaction": {
            "id": "tx-1",
            "kind": "withdrawal",
            "status": "pending_user_transfer_start",
            "amount_in": "20",
            "amount_out": "19.5",
            "amount_fee": "0.5",
            "more_info_url": "https://anchor.test/more/tx-1",
            "stellar_transaction_id": "abc123",
            "external_transaction_id": "rail-1",
            "message": "Waiting for your transfer",
        }
    }

    view = parse_transaction_view(payload)

    assert view.id == "tx-1"
    assert view.kind == "withdrawal"
    assert view.status == "pending_user_transfer_start"
    # Legacy status name maps to the modern wording key.
    assert view.status_i18n_key == "sep24_status_pending_user_transfer"
    assert view.amount_in == "20"
    assert view.amount_out == "19.5"
    assert view.amount_fee == "0.5"
    assert view.more_info_url == "https://anchor.test/more/tx-1"
    assert view.stellar_transaction_id == "abc123"
    assert view.external_transaction_id == "rail-1"
    assert view.message == "Waiting for your transfer"
    assert view.instructions is None


def test_parses_flat_payload_and_instructions():
    payload = {
        "id": "tx-2",
        "status": "pending_user_transfer_start",
        "instructions": {
            "amount_in": {
                "amount": "20",
                "asset": "stellar:yXLM:GISSUER",
                "destination": MUXED,
            }
        },
    }

    view = parse_transaction_view(payload, default_asset_code="yXLM")

    assert view.id == "tx-2"
    assert view.instructions is not None
    assert view.instructions.destination == MUXED
    assert view.instructions.is_muxed is True
    assert view.instructions.asset_code == "yXLM"
    assert view.instructions.memo is None


def test_missing_id_falls_back_to_dash_and_unknown_status():
    view = parse_transaction_view({"status": "some_new_status"})

    assert view.id == "-"
    assert view.status == "some_new_status"
    assert view.status_i18n_key == "sep24_status_unknown"


def test_legacy_withdraw_instructions_use_default_asset():
    payload = {
        "transaction": {
            "id": "tx-3",
            "status": "pending_user_transfer_start",
            "withdraw_anchor_account": "GANCHOR",
            "withdraw_memo": "3289",
            "withdraw_memo_type": "id",
        }
    }

    view = parse_transaction_view(
        payload, default_asset_code="USDM", default_asset_issuer="GISSUER"
    )

    assert view.instructions is not None
    assert view.instructions.destination == "GANCHOR"
    assert view.instructions.memo == "3289"
    assert view.instructions.asset_code == "USDM"
    assert view.instructions.asset_issuer == "GISSUER"


def test_awaits_user_transfer_helper():
    from core.models.sep24 import awaits_user_transfer

    assert awaits_user_transfer("pending_user_transfer_start") is True
    assert awaits_user_transfer("PENDING_USER_TRANSFER") is True
    assert awaits_user_transfer("incomplete") is True
    assert awaits_user_transfer("completed") is False
    assert awaits_user_transfer(None) is False
