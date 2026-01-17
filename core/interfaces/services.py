from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

class IStellarService(ABC):
    @abstractmethod
    async def get_account_details(self, public_key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve account details. 
        Returns a dictionary or object containing 'balances', 'sequence', 'signers', 'data', 'details', etc.
        """
        pass

    @abstractmethod
    async def get_selling_offers(self, public_key: str) -> List[Dict[str, Any]]:
        """Retrieve active selling offers for the account."""
        pass

    @abstractmethod
    async def submit_transaction(self, xdr: str) -> Dict[str, Any]:
        """Submit a signed transaction XDR to the Stellar network."""
        pass

    @abstractmethod
    async def build_payment_transaction(
        self, 
        source_account_id: str, 
        destination_account_id: str, 
        asset_code: str, 
        asset_issuer: Optional[str], 
        amount: str, 
        memo: Optional[str] = None,
        sequence: Optional[int] = None,
        cancel_offers: bool = False
    ) -> str:
        """Build a payment transaction XDR (unsigned)."""
        pass
    
    @abstractmethod
    async def check_account_exists(self, account_id: str) -> bool:
        """Check if an account exists on the network."""
        pass
