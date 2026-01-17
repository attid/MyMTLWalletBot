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
