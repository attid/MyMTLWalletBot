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
        asset_issuer: str | None, 
        amount: str, 
        memo: str | None = None,
        sequence: int | None = None,
        cancel_offers: bool = False,
        create_account: bool = False
    ) -> str:
        """Build a payment transaction XDR (unsigned)."""
        pass
    
    @abstractmethod
    async def check_account_exists(self, account_id: str) -> bool:
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
        path: list[Asset] = [],
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
        limit: str | None = None
    ) -> str:
        """Build a change trust transaction."""
        pass

    @abstractmethod
    async def build_manage_data_transaction(
        self,
        source_account_id: str,
        data: dict[str, str | None]
    ) -> str:
        """Build a transaction to manage data entries.
        
        Args:
            source_account_id: The source account ID.
            data: Dictionary of key-value pairs. Value=None means delete the data entry.
        """
        pass
    
    @abstractmethod
    async def sign_transaction(self, transaction_envelope: Any, secret: str) -> str:
        """Sign a transaction envelope with a secret key."""
        pass

    @abstractmethod
    async def sign_xdr(self, xdr: str, secret: str) -> str:
        """Sign a transaction XDR with a secret key."""
        pass
        
    @abstractmethod
    def create_payment_op(self, destination: str, asset_code: str, asset_issuer: str | None, amount: str, source: str | None = None) -> Any:
        """Create a payment operation."""
        pass

    @abstractmethod
    def create_create_account_op(self, destination: str, starting_balance: str, source: str | None = None) -> Any:
        """Create a create account operation."""
        pass

    @abstractmethod
    def create_change_trust_op(self, asset_code: str, asset_issuer: str, limit: str | None = None, source: str | None = None) -> Any:
        """Create a change trust operation."""
        pass

    @abstractmethod
    async def build_transaction(self, source_public_key: str, operations: list[Any], memo: str | None = None) -> Any:
        """Build a transaction with multiple operations."""
        pass

    @abstractmethod
    async def find_strict_send_path(
        self,
        source_asset: Asset,
        source_amount: str,
        destination_asset: Asset
    ) -> list[Asset]:
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

    @abstractmethod
    async def check_xdr(self, xdr: str, for_free_account: bool = False) -> str | None:
        """Check XDR validity."""
        pass

    @abstractmethod
    async def user_sign(self, session: Any, xdr: str, user_id: int, pin: str) -> str:
        """Sign XDR using user secrets."""
        pass

    @abstractmethod
    async def get_user_keypair(self, session: Any, user_id: int, pin: str) -> Any:
        """Get user keypair."""
        pass

    @abstractmethod
    async def get_user_account(self, session: Any, user_id: int) -> Any:
        """Get user account details."""
        pass

    @abstractmethod
    async def check_account(self, public_key: str) -> Any:
        """Check account details."""
        pass

    @abstractmethod
    async def is_free_wallet(self, session: Any, user_id: int) -> bool:
        """Check if wallet is free."""
        pass

    @abstractmethod
    async def change_password(self, session: Any, user_id: int, user_id_str: str, pin: str, pin_type: int) -> Any:
        """Change wallet password."""
        pass

    @abstractmethod
    async def send_xdr_async(self, xdr: str) -> dict[str, Any]:
        """Send transaction asynchronously."""
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
    
    @abstractmethod
    def from_mnemonic(self, mnemonic: str):
        """Import a wallet from a mnemonic."""
        pass

    @abstractmethod
    async def send_ton(self, to_address: str, amount_ton: Any, comment: str = "") -> str:
        """Send TON."""
        pass

    @abstractmethod
    async def send_usdt(self, to_address: str, amount_usdt: Any, comment: str = "") -> str:
        """Send USDT."""
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
