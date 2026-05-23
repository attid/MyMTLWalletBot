from dataclasses import dataclass
from enum import Enum
from typing import Any


class AnchorTransactionProtocol(str, Enum):
    SEP6 = "SEP-6"
    SEP24 = "SEP-24"


@dataclass(frozen=True)
class AnchorTransaction:
    protocol: AnchorTransactionProtocol
    id: str
    kind: str | None
    status: str | None
    amount_in: str | None = None
    amount_out: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    more_info_url: str | None = None

    @classmethod
    def from_raw(
        cls,
        protocol: AnchorTransactionProtocol,
        raw: dict[str, Any],
    ) -> "AnchorTransaction":
        return cls(
            protocol=protocol,
            id=str(raw.get("id") or raw.get("external_transaction_id") or "-"),
            kind=_optional_str(raw.get("kind")),
            status=_optional_str(raw.get("status")),
            amount_in=_optional_str(raw.get("amount_in")),
            amount_out=_optional_str(raw.get("amount_out")),
            started_at=_optional_str(raw.get("started_at")),
            updated_at=_optional_str(raw.get("updated_at")),
            completed_at=_optional_str(raw.get("completed_at")),
            more_info_url=_optional_str(raw.get("more_info_url")),
        )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
