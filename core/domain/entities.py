from dataclasses import dataclass
from typing import Optional

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
