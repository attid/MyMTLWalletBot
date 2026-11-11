"""Parse `GET /sep24/transaction` payloads into a renderable view."""

from typing import Any

from core.models.sep24 import Sep24TransactionView
from infrastructure.services.sep24.instructions import parse_payment_instructions


def parse_transaction_view(
    payload: dict[str, Any],
    *,
    default_asset_code: str | None = None,
    default_asset_issuer: str | None = None,
) -> Sep24TransactionView:
    """Build a view from the anchor response (`{transaction: {...}}` or flat)."""
    raw = payload.get("transaction")
    transaction = raw if isinstance(raw, dict) else payload

    instructions = parse_payment_instructions(
        transaction,
        default_asset_code=default_asset_code,
        default_asset_issuer=default_asset_issuer,
    )
    return Sep24TransactionView(
        id=str(transaction.get("id") or "-"),
        kind=_optional_str(transaction.get("kind")),
        status=_optional_str(transaction.get("status")),
        amount_in=_optional_str(transaction.get("amount_in")),
        amount_out=_optional_str(transaction.get("amount_out")),
        amount_fee=_optional_str(transaction.get("amount_fee")),
        more_info_url=_optional_str(transaction.get("more_info_url")),
        message=_optional_str(transaction.get("message")),
        instructions=instructions,
        stellar_transaction_id=_optional_str(transaction.get("stellar_transaction_id")),
        external_transaction_id=_optional_str(
            transaction.get("external_transaction_id")
        ),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
