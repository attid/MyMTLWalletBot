"""Parsers for anchor-provided SEP-24 payment instructions.

Real anchors return three different shapes (verified live, see
`../sep_anchor/docs/runbooks/live-sep24-golden-client.md`):

1. modern `instructions.amount_in = {destination, memo, memo_type, asset}`;
2. legacy `withdraw_anchor_account` / `withdraw_memo` / `withdraw_memo_type`;
3. nothing at all — the address only exists on the anchor's own `more_info_url`
   page, which the bot links to instead of scraping.

Two rules learned the hard way:

* a muxed `M...` destination must be paid verbatim — decoding it to a G-account
  plus an id memo makes anchors that match on `to_muxed_id` never see the
  payment;
* `hash` memos arrive base64-encoded from external anchors and must be decoded
  to hex before building a `HashMemo`.
"""

import base64
import binascii
import re
from typing import Any

from core.models.sep24 import PaymentInstructions, is_muxed_address

_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def is_muxed_destination(destination: str | None) -> bool:
    """True for a 69-character muxed `M...` Stellar account address."""
    return is_muxed_address(destination)


def parse_asset_ref(ref: Any) -> tuple[str | None, str | None]:
    """Parse `stellar:CODE:ISSUER`, `stellar:native` and `native` references."""
    if not ref:
        return None, None
    value = str(ref)
    if value.startswith("stellar:"):
        parts = value.split(":")[1:]
        if not parts or parts[0] in ("native", "XLM"):
            return None, None
        issuer = parts[1] if len(parts) > 1 else None
        return (parts[0], issuer) if issuer else (None, None)
    if value in ("native", "XLM"):
        return None, None
    return value, None


def decode_hash_memo(memo: str) -> str:
    """Return a hex memo hash, decoding the base64 form anchors send."""
    value = memo.strip()
    if _HEX_RE.match(value):
        return value.lower()
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), validate=False)
    except (binascii.Error, ValueError):
        return value
    # A Stellar hash memo is exactly 32 bytes; anything else is not a memo hash
    # and is kept verbatim so the operator can see what the anchor sent.
    if len(raw) == 32:
        return raw.hex()
    return value


def normalize_memo(
    memo_type: str | None, memo: str | None
) -> tuple[str | None, str | None]:
    """Normalize a memo pair, returning `(memo, memo_type)` or `(None, None)`."""
    if memo is None or memo == "":
        return None, None
    kind = (memo_type or "text").strip().lower()
    if kind == "hash":
        return decode_hash_memo(str(memo)), "hash"
    return str(memo), kind


def parse_payment_instructions(
    transaction: dict[str, Any],
    *,
    default_asset_code: str | None = None,
    default_asset_issuer: str | None = None,
) -> PaymentInstructions | None:
    """Extract the payment instructions from a SEP-24 transaction payload."""
    instructions = transaction.get("instructions") or {}
    amount_in = None
    if isinstance(instructions, dict):
        amount_in = instructions.get("amount_in") or instructions.get("amount_out")

    result: PaymentInstructions | None = None
    if isinstance(amount_in, dict) and amount_in.get("destination"):
        asset_code, asset_issuer = parse_asset_ref(amount_in.get("asset"))
        if asset_code is None:
            asset_code, asset_issuer = default_asset_code, default_asset_issuer
        result = PaymentInstructions(
            destination=str(amount_in["destination"]),
            asset_code=asset_code,
            asset_issuer=asset_issuer,
            amount=_optional_str(amount_in.get("amount")),
            source="instructions",
        )
        memo, memo_type = normalize_memo(
            amount_in.get("memo_type"), amount_in.get("memo")
        )
        result = _with_memo(result, memo, memo_type)
    elif transaction.get("withdraw_anchor_account"):
        asset_code, asset_issuer = parse_asset_ref(transaction.get("amount_in_asset"))
        if asset_code is None:
            asset_code, asset_issuer = default_asset_code, default_asset_issuer
        result = PaymentInstructions(
            destination=str(transaction["withdraw_anchor_account"]),
            asset_code=asset_code,
            asset_issuer=asset_issuer,
            amount=_optional_str(transaction.get("amount_in")),
            source="legacy",
        )
        memo, memo_type = normalize_memo(
            transaction.get("withdraw_memo_type"), transaction.get("withdraw_memo")
        )
        result = _with_memo(result, memo, memo_type)

    if result is None or not result.destination:
        return None
    if result.is_muxed:
        # The muxed address already carries the memo; adding a transaction memo
        # breaks anchors that match on `to_muxed_id`.
        result = _with_memo(result, None, None)
    return result


def _with_memo(
    instructions: PaymentInstructions, memo: str | None, memo_type: str | None
) -> PaymentInstructions:
    return PaymentInstructions(
        destination=instructions.destination,
        memo=memo,
        memo_type=memo_type,
        asset_code=instructions.asset_code,
        asset_issuer=instructions.asset_issuer,
        amount=instructions.amount,
        source=instructions.source,
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
