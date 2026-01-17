from typing import Optional
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from core.domain.entities import User
from core.interfaces.repositories import IUserRepository
from db.models import MyMtlWalletBotUsers

class SqlAlchemyUserRepository(IUserRepository):
    def __init__(self, session: Session):
        self.session = session

    async def get_by_id(self, user_id: int) -> Optional[User]:
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        result = self.session.execute(stmt)
        db_user = result.scalar_one_or_none()
        if db_user:
            return self._to_entity(db_user)
        return None

    async def create(self, user: User) -> User:
        db_user = MyMtlWalletBotUsers(
            user_id=user.id,
            user_name=user.username,
            lang=user.language,
            default_address=user.default_address
        )
        self.session.add(db_user)
        # Note: Commit is usually handled by the Unit of Work or higher level, 
        # but for now we might rely on auto-flush or manual commit calls in services/tests.
        # We'll assume the session manager handles commits.
        self.session.flush() 
        return self._to_entity(db_user)

    async def update(self, user: User) -> User:
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user.id)
        result = self.session.execute(stmt)
        db_user = result.scalar_one_or_none()
        if db_user:
            db_user.user_name = user.username
            db_user.lang = user.language
            db_user.default_address = user.default_address
            db_user.can_5000 = user.can_5000
            # session.add(db_user) is not strictly needed if it's already attached, but safe.
            self.session.flush()
            return self._to_entity(db_user)
        else:
            # Fallback to create if not exists? Or raise error? Repository pattern usually implies update updates existing.
            # For now, let's treat this strictly as update.
            raise ValueError(f"User with id {user.id} not found for update")

    async def get_account_by_username(self, username: str) -> tuple[Optional[str], Optional[int]]:
        """Get wallet public key and user_id by Telegram username."""
        from db.models import MyMtlWalletBot
        
        # Remove @ prefix and convert to lowercase
        clean_username = username.lower()[1:] if username.startswith('@') else username.lower()
        
        # First query to check the default_address
        stmt = select(MyMtlWalletBotUsers.user_id, MyMtlWalletBotUsers.default_address).where(
            MyMtlWalletBotUsers.user_name == clean_username
        )
        result = self.session.execute(stmt)
        user = result.one_or_none()
        
        if user is not None:
            user_id, default_address = user
            if default_address and len(default_address) == 56:
                return default_address, user_id
            else:
                # Second query if default_address is not available or invalid
                wallet_stmt = select(MyMtlWalletBot.public_key).where(
                    MyMtlWalletBot.user_id == user_id,
                    MyMtlWalletBot.default_wallet == 1
                )
                wallet_result = self.session.execute(wallet_stmt)
                wallet = wallet_result.scalar_one_or_none()
                if wallet is not None:
                    return wallet, user_id
        
        return None, None

    async def search_by_username(self, query: str) -> list[str]:
        """Search users by partial username match."""
        stmt = select(MyMtlWalletBotUsers.user_name).where(
            MyMtlWalletBotUsers.user_name.isnot(None),
            MyMtlWalletBotUsers.user_name.ilike(f"%{query}%")
        )
        result = self.session.execute(stmt)
        return [row[0] for row in result.all()]

    def _to_entity(self, db_user: MyMtlWalletBotUsers) -> User:
        return User(
            id=db_user.user_id,
            username=db_user.user_name,
            language=db_user.lang,
            default_address=db_user.default_address,
            can_5000=db_user.can_5000 or 0
        )
