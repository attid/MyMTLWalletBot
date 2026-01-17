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
