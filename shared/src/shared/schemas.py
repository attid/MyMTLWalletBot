"""Pydantic schemas for FastStream communication between bot and webapp."""

from pydantic import BaseModel


class PendingTxMessage(BaseModel):
    """Message published when a transaction needs signing via Web App."""

    tx_id: str
    user_id: int
    wallet_address: str
    unsigned_xdr: str
    memo: str


class TxSignedMessage(BaseModel):
    """Message published when a transaction has been signed in Web App."""

    tx_id: str
    user_id: int
