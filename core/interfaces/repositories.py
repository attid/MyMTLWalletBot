from abc import ABC, abstractmethod
from typing import List, Optional
from core.domain.entities import User, Wallet

class IUserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Retrieve a user by their Telegram ID."""
        pass

    @abstractmethod
    async def create(self, user: User) -> User:
        """Create a new user."""
        pass
    
    @abstractmethod
    async def update(self, user: User) -> User:
        """Update an existing user."""
        pass

    @abstractmethod
    async def get_account_by_username(self, username: str) -> tuple[Optional[str], Optional[int]]:
        """Get wallet public key and user_id by Telegram username.
        
        Args:
            username: Telegram username starting with '@'
            
        Returns:
            Tuple of (public_key, user_id) or (None, None) if not found
        """
        pass

    @abstractmethod
    async def search_by_username(self, query: str) -> List[str]:
        """Search users by partial username match. Returns list of usernames."""
        pass

class IWalletRepository(ABC):
    @abstractmethod
    async def get_by_user_id(self, user_id: int) -> List[Wallet]:
        """Retrieve all wallets belonging to a user."""
        pass

    @abstractmethod
    async def get_all_active(self, user_id: int) -> List[Wallet]:
        """Retrieve all active (non-deleted) wallets for a user."""
        pass

    @abstractmethod
    async def get_by_public_key(self, public_key: str) -> Optional[Wallet]:
        """Retrieve a wallet by its public key."""
        pass

    @abstractmethod
    async def get_default_wallet(self, user_id: int) -> Optional[Wallet]:
        """Retrieve the default wallet for a user."""
        pass
    
    @abstractmethod
    async def create(self, wallet: Wallet) -> Wallet:
        """Create a new wallet."""
        pass
    
    @abstractmethod
    async def update(self, wallet: Wallet) -> Wallet:
        """Update an existing wallet."""
        pass

    @abstractmethod
    async def delete(self, user_id: int, public_key: str, erase: bool = False, wallet_id: int = None) -> None:
        """Delete or soft-delete a wallet."""
        pass

    @abstractmethod
    async def get_info(self, user_id: int, public_key: str) -> str:
        """Get wallet info string (pin type, free wallet, etc)."""
        pass

    @abstractmethod
    async def reset_balance_cache(self, user_id: int) -> None:
        """Reset the cached balance for the user's default wallet.
        
        This invalidates the local balance cache, forcing a refresh 
        from the network on next balance request.
        """
        pass


class IAddressBookRepository(ABC):
    """Interface for address book operations."""
    
    @abstractmethod
    async def get_all(self, user_id: int) -> List['AddressBookEntry']:
        """Get all address book entries for a user."""
        pass
    
    @abstractmethod
    async def get_by_id(self, entry_id: int, user_id: int) -> Optional['AddressBookEntry']:
        """Get a specific address book entry."""
        pass
    
    @abstractmethod
    async def create(self, user_id: int, address: str, name: str) -> 'AddressBookEntry':
        """Create a new address book entry."""
        pass
    
    @abstractmethod
    async def delete(self, entry_id: int, user_id: int) -> None:
        """Delete an address book entry."""
        pass


class IChequeRepository(ABC):
    """Interface for cheque operations."""
    
    @abstractmethod
    async def create(self, uuid: str, amount: str, count: int, user_id: int, comment: str) -> 'Cheque':
        """Create a new cheque."""
        pass
    
    @abstractmethod
    async def get_by_uuid(self, uuid: str, user_id: int = None) -> Optional['Cheque']:
        """Get a cheque by UUID."""
        pass
    
    @abstractmethod
    async def get_receive_count(self, uuid: str, user_id: int = None) -> int:
        """Get the number of times a cheque has been received."""
        pass
    
    @abstractmethod
    async def get_available(self, user_id: int) -> List['Cheque']:
        """Get all available (not fully claimed) cheques for a user."""
        pass
    
    @abstractmethod
    async def add_history(self, cheque_id: int, user_id: int) -> None:
        """Record a cheque claim in history."""
        pass
