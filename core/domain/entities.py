from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: int
    username: Optional[str]
    language: str
    default_address: Optional[str] = None

@dataclass
class Wallet:
    id: int
    user_id: int
    public_key: str
    is_default: bool
    is_free: bool
    name: Optional[str] = None
    assets_visibility: Optional[str] = "{}"
