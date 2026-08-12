"""Shared constants for FastStream queues, Redis keys, and TX statuses."""

# FastStream queues (Redis lists)
QUEUE_TX_SIGNED = "tx_signed"
QUEUE_SEALEDBOX_COMPLETED = "sealedbox_completed"

# Redis keys
REDIS_TX_PREFIX = "tx:"
REDIS_TX_TTL = 600  # 10 minutes
REDIS_SEALEDBOX_PREFIX = "sealedbox:request:"
REDIS_SEALEDBOX_USER_PREFIX = "sealedbox:user:"
REDIS_SEALEDBOX_TTL = 600

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
FIELD_SUB_INVOCATION_SUMMARY = "sub_invocation_summary"
FIELD_SEALEDBOX_CIPHERTEXT = "ciphertext"
FIELD_SEALEDBOX_OUTPUT_FILENAME = "output_filename"

# Request statuses
STATUS_PENDING = "pending"
STATUS_SIGNED = "signed"
STATUS_EXPIRED = "expired"
STATUS_ERROR = "error"
STATUS_COMPLETED = "completed"
