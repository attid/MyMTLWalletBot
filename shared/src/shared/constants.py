"""Shared constants for FastStream channels, Redis keys, and TX statuses."""

# FastStream channels
CHANNEL_TX_PENDING = "tx_pending"
CHANNEL_TX_SIGNED = "tx_signed"

# Redis keys
REDIS_TX_PREFIX = "tx:"
REDIS_TX_TTL = 600  # 10 minutes

# Redis Hash fields
FIELD_USER_ID = "user_id"
FIELD_WALLET_ADDRESS = "wallet_address"
FIELD_UNSIGNED_XDR = "unsigned_xdr"
FIELD_MEMO = "memo"
FIELD_STATUS = "status"
FIELD_SIGNED_XDR = "signed_xdr"
FIELD_CREATED_AT = "created_at"
FIELD_ERROR = "error"

# TX statuses
STATUS_PENDING = "pending"
STATUS_SIGNED = "signed"
STATUS_EXPIRED = "expired"
STATUS_ERROR = "error"
