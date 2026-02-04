"""Shared schemas and constants for MMWB bot and webapp."""

from shared.schemas import PendingTxMessage, TxSignedMessage
from shared.constants import (
    CHANNEL_TX_PENDING,
    CHANNEL_TX_SIGNED,
    REDIS_TX_PREFIX,
    REDIS_TX_TTL,
    FIELD_USER_ID,
    FIELD_WALLET_ADDRESS,
    FIELD_UNSIGNED_XDR,
    FIELD_MEMO,
    FIELD_STATUS,
    FIELD_SIGNED_XDR,
    FIELD_CREATED_AT,
    FIELD_ERROR,
    STATUS_PENDING,
    STATUS_SIGNED,
    STATUS_EXPIRED,
    STATUS_ERROR,
)

__all__ = [
    "PendingTxMessage",
    "TxSignedMessage",
    "CHANNEL_TX_PENDING",
    "CHANNEL_TX_SIGNED",
    "REDIS_TX_PREFIX",
    "REDIS_TX_TTL",
    "FIELD_USER_ID",
    "FIELD_WALLET_ADDRESS",
    "FIELD_UNSIGNED_XDR",
    "FIELD_MEMO",
    "FIELD_STATUS",
    "FIELD_SIGNED_XDR",
    "FIELD_CREATED_AT",
    "FIELD_ERROR",
    "STATUS_PENDING",
    "STATUS_SIGNED",
    "STATUS_EXPIRED",
    "STATUS_ERROR",
]
