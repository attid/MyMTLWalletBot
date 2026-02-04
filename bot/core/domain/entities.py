from dataclasses import dataclass
from typing import Optional
from enum import Enum

class ChequeStatus(Enum):
    CHEQUE = 0
    CANCELED = 1
    INVOICE = 2


@dataclass
class User:
    id: int
    username: Optional[str]
    language: str
    default_address: Optional[str] = None
    can_5000: int = 0  # 0=limit enabled, 1=limit disabled

@dataclass
class Wallet:
    id: int
    user_id: int
    public_key: str
    is_default: bool
    is_free: bool
    use_pin: int = 0  # 0=no pin, 1=pin, 2=password, 10=read-only
    name: Optional[str] = None
    assets_visibility: Optional[str] = "{}"
    secret_key: Optional[str] = None
    seed_key: Optional[str] = None
    balances: Optional[list] = None # List[Balance]
    balances_event_id: str = "0"
    last_event_id: str = "0"

@dataclass
class AddressBookEntry:
    id: int
    user_id: int
    address: str
    name: str

@dataclass
class Cheque:
    id: int
    uuid: str
    user_id: int
    amount: str
    count: int
    comment: Optional[str]
    status: int
    asset: Optional[str] = "EURMTL:GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"

@dataclass
class ChequeHistory:
    id: int
    cheque_id: int
    user_id: int
    dt_block: Optional[str]
