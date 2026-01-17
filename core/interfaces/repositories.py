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

class IWalletRepository(ABC):
    @abstractmethod
    async def get_by_user_id(self, user_id: int) -> List[Wallet]:
        """Retrieve all wallets belonging to a user."""
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
    async def reset_balance_cache(self, user_id: int) -> None:
        """Reset the cached balance for the user's default wallet.
        
        This invalidates the local balance cache, forcing a refresh 
        from the network on next balance request.
        """
        pass
