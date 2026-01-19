from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple
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
    async def build_manage_data_transaction(
        self,
        source_account_id: str,
        data: Dict[str, Optional[str]]
    ) -> str:
        """Build a transaction to manage data entries.
        
        Args:
            source_account_id: The source account ID.
            data: Dictionary of key-value pairs. Value=None means delete the data entry.
        """
        pass
    
    @abstractmethod
    async def sign_transaction(self, transaction_envelope, secret: str) -> str:
        """Sign a transaction envelope with a secret key."""
        pass

    @abstractmethod
    async def sign_xdr(self, xdr: str, secret: str) -> str:
        """Sign a transaction XDR with a secret key."""
        pass
        
    @abstractmethod
    def create_payment_op(self, destination: str, asset_code: str, asset_issuer: Optional[str], amount: str, source: Optional[str] = None):
        """Create a payment operation."""
        pass

    @abstractmethod
    def create_create_account_op(self, destination: str, starting_balance: str, source: Optional[str] = None):
        """Create a create account operation."""
        pass

    @abstractmethod
    def create_change_trust_op(self, asset_code: str, asset_issuer: str, limit: str = None, source: Optional[str] = None):
        """Create a change trust operation."""
        pass

    @abstractmethod
    async def build_transaction(self, source_public_key: str, operations: list, memo: str = None):
        """Build a transaction with multiple operations."""
        pass

    @abstractmethod
    async def find_strict_send_path(
        self,
        source_asset: Asset,
        source_amount: str,
        destination_asset: Asset
    ) -> List[Asset]:
        """Find a strict send payment path."""
        pass

    @abstractmethod
    def generate_keypair(self) -> Any:
        """Generate a random keypair."""
        pass

    @abstractmethod
    def get_keypair_from_secret(self, secret_key: str) -> Any:
        """Get keypair from secret key."""
        pass

    @abstractmethod
    def generate_mnemonic(self) -> str:
        """Generate a random mnemonic phrase."""
        pass

    @abstractmethod
    def get_keypair_from_mnemonic(self, mnemonic: str) -> Any:
        """Get keypair from mnemonic phrase."""
        pass


class ITonService(ABC):
    @abstractmethod
    def create_wallet(self):
        """Create a new TON wallet (Stateful)."""
        pass
    
    @abstractmethod
    def generate_wallet(self) -> Tuple[Any, List[str]]:
        """Generate a new TON wallet returning (wallet_obj, mnemonic) without storing state."""
        pass
    
    @property
    def wallet(self):
        """Get the wallet object."""
        return None
        
    @property
    def mnemonic(self) -> Optional[str]:
        """Get the mnemonic phrase."""
        return None



class IEncryptionService(ABC):
    @abstractmethod
    def encrypt(self, data: str, key: str) -> str:
        """Encrypt data using a key."""
        pass

    @abstractmethod
    def decrypt(self, encrypted_data: str, key: str) -> Optional[str]:
        """Decrypt data using a key. Returns None if decryption fails."""
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
