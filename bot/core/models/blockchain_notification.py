"""Serializable blockchain notification values for durable delivery."""

import json
import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, TypeAlias


NotificationPrimitive: TypeAlias = str | int | float | bool | None
NotificationData: TypeAlias = Mapping[str, NotificationPrimitive]


@dataclass(frozen=True)
class BlockchainNotification:
    """A Redis-safe blockchain event with a stable idempotency identity."""

    notification_id: str
    user_id: int
    event_type: str
    text: str
    created_at: int
    transaction_hash: str
    event_index: int
    data: NotificationData = field(default_factory=dict)
    idempotency_key: str = field(init=False)

    def __post_init__(self) -> None:
        self._validate_non_empty_str(self.notification_id, "notification_id")
        self._validate_int(self.user_id, "user_id")
        self._validate_non_empty_str(self.event_type, "event_type")
        self._validate_non_empty_str(self.text, "text")
        self._validate_int(self.created_at, "created_at")
        self._validate_non_empty_str(self.transaction_hash, "transaction_hash")
        self._validate_int(self.event_index, "event_index")
        if self.event_index < 0:
            raise ValueError("event_index must not be negative")
        object.__setattr__(self, "idempotency_key", self._build_idempotency_key())
        if not isinstance(self.data, dict):
            raise TypeError("notification data must be an object")
        for key, value in self.data.items():
            if not isinstance(key, str):
                raise TypeError("notification data keys must be strings")
            if isinstance(value, (dict, list, tuple)):
                raise TypeError("notification data must contain only stable primitives")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise TypeError("notification data must contain only stable primitives")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("notification data floats must be finite")
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))

    def to_json(self) -> str:
        """Serialize deterministically so Redis comparisons are exact."""
        return json.dumps(
            {
                "notification_id": self.notification_id,
                "user_id": self.user_id,
                "idempotency_key": self.idempotency_key,
                "event_type": self.event_type,
                "text": self.text,
                "created_at": self.created_at,
                "transaction_hash": self.transaction_hash,
                "event_index": self.event_index,
                "data": dict(self.data),
            },
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, value: str) -> "BlockchainNotification":
        """Deserialize a notification previously stored by :meth:`to_json`."""
        decoded = json.loads(value, parse_constant=cls._reject_non_finite_json_constant)
        if not isinstance(decoded, dict):
            raise TypeError("notification JSON must contain an object")
        data = decoded.get("data")
        if not isinstance(data, dict):
            raise TypeError("notification data must be an object")
        notification = cls(
            notification_id=cls._require_str(decoded, "notification_id"),
            user_id=cls._require_int(decoded, "user_id"),
            event_type=cls._require_str(decoded, "event_type"),
            text=cls._require_str(decoded, "text"),
            created_at=cls._require_int(decoded, "created_at"),
            transaction_hash=cls._require_str(decoded, "transaction_hash"),
            event_index=cls._require_int(decoded, "event_index"),
            data=data,
        )
        if cls._require_str(decoded, "idempotency_key") != notification.idempotency_key:
            raise ValueError("idempotency_key does not match notification identity")
        return notification

    def _build_idempotency_key(self) -> str:
        return f"{self.transaction_hash}:{self.event_type}:{self.event_index}:{self.user_id}"

    @staticmethod
    def _validate_non_empty_str(value: object, field: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"{field} must be a string")
        if not value:
            raise ValueError(f"{field} must not be empty")

    @staticmethod
    def _validate_int(value: object, field: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field} must be an integer")

    @staticmethod
    def _require_str(value: dict[object, object], field: str) -> str:
        field_value = value.get(field)
        BlockchainNotification._validate_non_empty_str(field_value, field)
        assert isinstance(field_value, str)
        return field_value

    @staticmethod
    def _require_int(value: dict[object, object], field: str) -> int:
        field_value = value.get(field)
        BlockchainNotification._validate_int(field_value, field)
        assert isinstance(field_value, int) and not isinstance(field_value, bool)
        return field_value

    @staticmethod
    def _reject_non_finite_json_constant(value: str) -> None:
        raise ValueError(f"notification JSON contains non-finite number {value}")
