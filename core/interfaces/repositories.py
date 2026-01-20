from abc import ABC, abstractmethod
from typing import List, Optional, Any, TYPE_CHECKING, Callable
from core.domain.entities import User, Wallet, AddressBookEntry, Cheque

if TYPE_CHECKING:
    from db.models import NotificationFilter, TOperations, MyMtlWalletBotMessages

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
    async def update_lang(self, user_id: int, lang: str):
        """Update user language."""
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

    @abstractmethod
    async def update_donate_sum(self, user_id: int, amount: float) -> None:
        """Add to the user's donation sum."""
        pass

    @abstractmethod
    async def delete(self, user_id: int) -> None:
        """Delete a user."""
        pass

    @abstractmethod
    async def get_usdt_key(self, user_id: int, create_func: Optional[Callable] = None, user_name: Optional[str] = None) -> tuple[Optional[str], int]:
        """Get or create user's USDT private key and balance."""
        pass

    @abstractmethod
    async def set_usdt_key(self, user_id: int, address: str) -> None:
        """Set USDT address."""
        pass
        
    @abstractmethod
    async def update_usdt_balance(self, user_id: int, amount: int) -> str:
        """Update USDT balance and return address."""
        pass

    @abstractmethod
    async def get_btc_uuid(self, user_id: int) -> tuple[Optional[str], Optional[object]]: # datetime
        """Get BTC UUID and date."""
        pass

    @abstractmethod
    async def set_btc_uuid(self, user_id: int, uuid: Optional[str]) -> None:
        """Set BTC UUID."""
        pass
        
    @abstractmethod
    async def get_all_with_usdt_balance(self) -> List[tuple[str, int, int]]:
        """Get all users with +ve USDT balance. Returns [(username, amount, user_id)]."""
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
    async def count_free_wallets(self, user_id: int) -> int:
        """Count the number of active free wallets for a user."""
        pass

    @abstractmethod
    async def get_by_public_key(self, public_key: str) -> Optional[Wallet]:
        """Retrieve a wallet by its public key."""
        pass

    @abstractmethod
    async def get_by_id(self, wallet_id: int) -> Optional[Wallet]:
        """Retrieve a wallet by its ID."""
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
    async def set_default_wallet(self, user_id: int, public_key: str) -> bool:
        """Set a wallet as default for the user."""
        pass

    @abstractmethod
    async def delete(self, user_id: int, public_key: str, erase: bool = False, wallet_id: Optional[int] = None) -> None:
        """Delete or soft-delete a wallet."""
        pass
    
    @abstractmethod
    async def delete_all_by_user(self, user_id: int) -> None:
        """Delete (soft-delete) all wallets for a user."""
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
        
    @abstractmethod
    async def get_all_deleted(self) -> List[Wallet]:
        """Get all wallets marked for deletion."""
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
    async def get_by_uuid(self, uuid: str, user_id: Optional[int] = None) -> Optional['Cheque']:
        """Get a cheque by UUID."""
        pass
    
    @abstractmethod
    async def get_receive_count(self, uuid: str, user_id: Optional[int] = None) -> int:
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

    @abstractmethod
    async def cancel(self, cheque_uuid: str, user_id: int) -> bool:
        """Cancel a cheque (set status to CANCELED)."""
        pass


class INotificationRepository(ABC):
    """Interface for notification filter operations."""

    @abstractmethod
    async def get_by_user_id(self, user_id: int) -> List['NotificationFilter']:
        """Get all notification filters for a user."""
        pass

    @abstractmethod
    async def create(self, user_id: int, public_key: Optional[str], asset_code: Optional[str], 
                    min_amount: float, operation_type: str) -> 'NotificationFilter':
        """Create a new notification filter."""
        pass

    @abstractmethod
    async def delete_all_by_user(self, user_id: int) -> None:
        """Delete all notification filters for a user."""
        pass
    
    @abstractmethod
    async def find_duplicate(self, user_id: int, public_key: Optional[str], asset_code: Optional[str], 
                           min_amount: float, operation_type: str) -> Optional['NotificationFilter']:
        """Find a duplicate filter."""
        pass


class IOperationRepository(ABC):
    """Interface for operation (transaction) retrieval."""
    
    @abstractmethod
    async def get_by_id(self, operation_id: str) -> Optional['TOperations']:
        """Retrieve an operation by its ID."""
        pass

    @abstractmethod
    async def get_recent_for_addresses(self, addresses: List[str], last_event_id: int, 
                                     minutes: int = 30) -> List['TOperations']:
        """Get recent operations for a list of addresses efficiently."""
        pass
    
    @abstractmethod
    async def get_by_account_since_id(self, account: str, last_id: int, minutes: int = 30) -> List['TOperations']:
        """Get operations for a specific account since a given ID."""
        pass


class IMessageRepository(ABC):
    """Interface for message queue operations."""
    
    @abstractmethod
    async def enqueue(self, user_id: int, text: str, use_alarm: int = 0, update_id: Optional[int] = None, button_json: Optional[str] = None) -> None:
        """Add a message to the send queue."""
        pass
    
    @abstractmethod
    async def get_unsent(self, limit: int = 10) -> List['MyMtlWalletBotMessages']:
        """Get a batch of unsent messages."""
        pass
    
    @abstractmethod
    async def mark_sent(self, message_id: int) -> None:
        """Mark a message as sent."""
        pass
        
    @abstractmethod
    async def mark_failed(self, message_id: int) -> None:
        """Mark a message as failed (or retry later)."""
        pass


class IRepositoryFactory(ABC):
    """Abstract Factory for creating repositories."""

    @abstractmethod
    def get_wallet_repository(self, session: Any) -> IWalletRepository:
        pass

    @abstractmethod
    def get_user_repository(self, session: Any) -> IUserRepository:
        pass

    @abstractmethod
    def get_addressbook_repository(self, session: Any) -> IAddressBookRepository:
        pass

    @abstractmethod
    def get_cheque_repository(self, session: Any) -> IChequeRepository:
        pass
    
    @abstractmethod
    def get_notification_repository(self, session: Any) -> INotificationRepository:
        pass

    @abstractmethod
    def get_operation_repository(self, session: Any) -> IOperationRepository:
        pass

    @abstractmethod
    def get_message_repository(self, session: Any) -> IMessageRepository:
        pass
