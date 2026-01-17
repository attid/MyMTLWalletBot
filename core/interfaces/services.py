from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from core.domain.value_objects import Asset

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
    def check_account_exists(self, account_id: str) -> bool:
        """Check if an account exists on the network."""
        pass

    @abstractmethod
    async def swap_assets(
        self,
        source_account_id: str,
        send_asset: Asset,
        send_amount: str,
        receive_asset: Asset,
        receive_amount: str,
        path: List[Asset] = [],
        strict_receive: bool = False,
        cancel_offers: bool = False
    ) -> str:
        """Build a path payment transaction (strict send or strict receive)."""
        pass

    @abstractmethod
    async def manage_offer(
        self,
        source_account_id: str,
        selling: Asset,
        buying: Asset,
        amount: str,
        price: str,
        offer_id: int = 0
    ) -> str:
        """Build a manage offer transaction."""
        pass

    @abstractmethod
    async def build_change_trust_transaction(
        self,
        source_account_id: str,
        asset_code: str,
        asset_issuer: str,
        limit: Optional[str] = None
    ) -> str:
        """Build a change trust transaction."""
        pass
    
    @abstractmethod
    def sign_transaction(self, xdr: str, secret_key: str) -> str:
        """Sign a transaction XDR with a secret key."""
        pass


class IWalletSecretService(ABC):
    """Interface for secure wallet secret access.
    
    This service provides access to sensitive wallet data that should not
    be part of the domain entity for security reasons.
    """
    
    @abstractmethod
    async def get_wallet_type(self, user_id: int) -> Optional[str]:
        """
        Get the wallet type identifier.
        Returns 'TON' for TON wallets, or the secret_key identifier for Stellar.
        """
        pass
    
    @abstractmethod
    async def get_ton_mnemonic(self, user_id: int) -> Optional[str]:
        """
        Get the TON wallet mnemonic (seed_key) for the user's default wallet.
        Returns None if not a TON wallet.
        """
        pass
    
    @abstractmethod
    async def is_ton_wallet(self, user_id: int) -> bool:
        """Check if the user's default wallet is a TON wallet."""
        pass
