import base64

from infrastructure.services.sep24.instructions import (
    decode_hash_memo,
    is_muxed_destination,
    normalize_memo,
    parse_asset_ref,
    parse_payment_instructions,
)

MUXED = "MCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYKAAAAAAAAAA73IMRS"
GADDR = "GCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYLQDJ"


def test_modern_instructions_with_asset_ref():
    tx = {
        "instructions": {
            "amount_in": {
                "amount": "10",
                "asset": "stellar:yXLM:GARDNV3Q7YGT4AKSDF25LT32YSCCW4EV22Y2TV3I2PU2MMXJTEDL5T55",
                "destination": GADDR,
                "memo": "3289",
                "memo_type": "id",
            }
        }
    }

    instructions = parse_payment_instructions(tx)

    assert instructions is not None
    assert instructions.destination == GADDR
    assert instructions.asset_code == "yXLM"
    assert instructions.asset_issuer.startswith("GARDNV")
    assert instructions.memo == "3289"
    assert instructions.memo_type == "id"
    assert instructions.source == "instructions"


def test_legacy_withdraw_anchor_account_shape():
    tx = {
        "withdraw_anchor_account": GADDR,
        "withdraw_memo": "hello",
        "withdraw_memo_type": "text",
        "amount_in": "20",
    }

    instructions = parse_payment_instructions(
        tx, default_asset_code="yXLM", default_asset_issuer="GISSUER"
    )

    assert instructions is not None
    assert instructions.source == "legacy"
    assert instructions.destination == GADDR
    assert instructions.memo == "hello"
    assert instructions.asset_code == "yXLM"
    assert instructions.amount == "20"


def test_muxed_destination_is_kept_verbatim_without_memo():
    tx = {
        "withdraw_anchor_account": MUXED,
        "withdraw_memo": "3289",
        "withdraw_memo_type": "id",
    }

    instructions = parse_payment_instructions(tx)

    assert instructions is not None
    assert instructions.destination == MUXED
    assert instructions.is_muxed is True
    assert instructions.memo is None
    assert instructions.memo_type is None


def test_base64_hash_memo_is_decoded_to_hex():
    raw = bytes(range(32))
    encoded = base64.b64encode(raw).decode()
    tx = {
        "instructions": {
            "amount_in": {
                "destination": GADDR,
                "memo": encoded,
                "memo_type": "hash",
            }
        }
    }

    instructions = parse_payment_instructions(tx)

    assert instructions is not None
    assert instructions.memo == raw.hex()
    assert instructions.memo_type == "hash"


def test_hash_memo_already_in_hex_is_normalized():
    memo = "A" * 64
    assert decode_hash_memo(memo) == memo.lower()


def test_missing_destination_returns_none():
    assert parse_payment_instructions({}) is None
    assert parse_payment_instructions({"instructions": {}}) is None


def test_asset_ref_parsing():
    assert parse_asset_ref("stellar:native") == (None, None)
    assert parse_asset_ref("native") == (None, None)
    assert parse_asset_ref("stellar:USDM:GISSUER") == ("USDM", "GISSUER")
    assert parse_asset_ref(None) == (None, None)


def test_memo_normalization_keeps_empty_memo_out():
    assert normalize_memo("text", "") == (None, None)
    assert normalize_memo(None, "abc") == ("abc", "text")


def test_muxed_detection():
    assert is_muxed_destination(MUXED) is True
    assert is_muxed_destination(GADDR) is False
    assert is_muxed_destination(None) is False


def test_non_32_byte_hash_is_kept_verbatim():
    import base64

    encoded = base64.b64encode(bytes(range(64))).decode()

    assert decode_hash_memo(encoded) == encoded
    assert is_muxed_destination("M" + "A" * 68) is True
    assert is_muxed_destination("Mnot-really-muxed") is False
