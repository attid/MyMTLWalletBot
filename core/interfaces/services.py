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
