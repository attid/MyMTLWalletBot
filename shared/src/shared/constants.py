"""Shared constants for FastStream queues, Redis keys, and TX statuses."""

# FastStream queues (Redis lists)
QUEUE_TX_SIGNED = "tx_signed"

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
FIELD_FSM_AFTER_SEND = "fsm_after_send"
FIELD_SUCCESS_MSG = "success_msg"

# TX statuses
STATUS_PENDING = "pending"
STATUS_SIGNED = "signed"
STATUS_EXPIRED = "expired"
STATUS_ERROR = "error"
