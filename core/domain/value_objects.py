from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Balance:
    asset_code: str
    asset_issuer: Optional[str]
    asset_type: str
    balance: str
    buying_liabilities: str = "0"
    selling_liabilities: str = "0"
    limit: Optional[str] = None
    
    @property
    def is_native(self) -> bool:
        return self.asset_type == "native"

@dataclass(frozen=True)
class Asset:
    code: str
    issuer: Optional[str] = None
    
    @property
    def is_native(self) -> bool:
        return self.code == "XLM" and self.issuer is None

    def to_string(self) -> str:
        if self.is_native:
            return "XLM"
        return f"{self.code}:{self.issuer}"

@dataclass(frozen=True)
class PaymentResult:
    success: bool
    xdr: Optional[str] = None
    transaction_hash: Optional[str] = None
    error_message: Optional[str] = None
