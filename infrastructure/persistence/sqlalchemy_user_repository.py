from typing import Optional, List, Callable
from datetime import datetime, timedelta
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.domain.entities import User
from core.interfaces.repositories import IUserRepository
from db.models import MyMtlWalletBotUsers
from other.tron_tools import create_trc_private_key

class SqlAlchemyUserRepository(IUserRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> Optional[User]:
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        result = await self.session.execute(stmt)
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
        await self.session.flush() 
        return self._to_entity(db_user)

    async def update(self, user: User) -> User:
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user.id)
        result = await self.session.execute(stmt)
        db_user = result.scalar_one_or_none()
        if db_user:
            db_user.user_name = user.username
            db_user.lang = user.language
            db_user.default_address = user.default_address
            db_user.can_5000 = user.can_5000
            # session.add(db_user) is not strictly needed if it's already attached, but safe.
            await self.session.flush()
            return self._to_entity(db_user)
        else:
            # Fallback to create if not exists? Or raise error? Repository pattern usually implies update updates existing.
            # For now, let's treat this strictly as update.
            raise ValueError(f"User with id {user.id} not found for update")

    async def update_lang(self, user_id: int, lang: str):
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.lang = lang
        else:
            user = MyMtlWalletBotUsers(user_id=user_id, lang=lang)
            self.session.add(user)
        await self.session.flush()

    async def get_account_by_username(self, username: str) -> tuple[Optional[str], Optional[int]]:
        """Get wallet public key and user_id by Telegram username."""
        from db.models import MyMtlWalletBot
        
        # Remove @ prefix and convert to lowercase
        clean_username = username.lower()[1:] if username.startswith('@') else username.lower()
        
        # First query to check the default_address
        stmt = select(MyMtlWalletBotUsers.user_id, MyMtlWalletBotUsers.default_address).where(
            MyMtlWalletBotUsers.user_name == clean_username
        )
        result = await self.session.execute(stmt)
        user = result.one_or_none()
        
        if user is not None:
            user_id, default_address = user
            if default_address and len(default_address) == 56:
                return default_address, user_id
            else:
                # Second query if default_address is not available or invalid
                wallet_stmt = select(MyMtlWalletBot.public_key).where(
                    MyMtlWalletBot.user_id == user_id
                ).where(
                    MyMtlWalletBot.default_wallet == 1
                )
                wallet_result = await self.session.execute(wallet_stmt)
                wallet = wallet_result.scalar_one_or_none()
                if wallet is not None:
                    return wallet, user_id
        
        return None, None

    async def search_by_username(self, query: str) -> list[str]:
        """Search users by partial username match."""
        stmt = select(MyMtlWalletBotUsers.user_name).where(
            MyMtlWalletBotUsers.user_name.isnot(None)
        ).where(
            MyMtlWalletBotUsers.user_name.ilike(f"%{query}%")
        )
        result = await self.session.execute(stmt)
        return [str(row[0]) for row in result.all() if row[0]]

    async def update_donate_sum(self, user_id: int, amount: float) -> None:
        """Add to the user's donation sum."""
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        result = await self.session.execute(stmt)
        db_user = result.scalar_one_or_none()
        if db_user:
            current_sum = float(db_user.donate_sum or 0.0)
            db_user.donate_sum = current_sum + amount  # type: ignore
            await self.session.flush()

    async def delete(self, user_id: int) -> None:
        """Delete a user."""
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        result = await self.session.execute(stmt)
        db_user = result.scalar_one_or_none()
        if db_user:
            await self.session.delete(db_user)
            await self.session.flush()

    async def get_usdt_key(self, user_id: int, create_func: Optional[Callable] = None, user_name: Optional[str] = None) -> tuple[Optional[str], int]:
        if user_id > 0:
            stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        elif user_name:
            stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_name == user_name)
        else:
            return None, 0
            
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user and user.usdt and len(user.usdt) == 64:
            return user.usdt, user.usdt_amount or 0
        elif user:
            # Generate new key if user exists but has no USDT key
            try:
                addr = create_func() if create_func else create_trc_private_key()
                user.usdt = addr
                await self.session.flush() 
                return addr, 0
            except Exception:
                return None, 0
        return None, 0

    async def set_usdt_key(self, user_id: int, address: str) -> None:
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.usdt = address
            await self.session.flush()

    async def update_usdt_balance(self, user_id: int, amount: int) -> str:
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user and user.usdt and len(user.usdt) == 64:
            current_amount = user.usdt_amount or 0
            user.usdt_amount = current_amount + amount
            await self.session.flush()
            return str(user.usdt)
        else:
             raise ValueError(f"No user found with id {user_id} or invalid USDT key")

    async def get_btc_uuid(self, user_id: int) -> tuple[Optional[str], Optional[datetime]]:
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user and user.btc and user.btc_date and len(user.btc) > 10:
            return user.btc, user.btc_date
        return None, None

    async def set_btc_uuid(self, user_id: int, uuid: Optional[str]) -> None:
        stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.btc = uuid
            user.btc_date = datetime.now() + timedelta(minutes=30)
            await self.session.flush()

    async def get_all_with_usdt_balance(self) -> List[tuple[str, int, int]]:
        stmt = select(MyMtlWalletBotUsers.user_name, MyMtlWalletBotUsers.usdt_amount, MyMtlWalletBotUsers.user_id).where(
            MyMtlWalletBotUsers.usdt_amount > 0
        ).order_by(MyMtlWalletBotUsers.usdt_amount.desc())
        result = await self.session.execute(stmt)
        return [(row.user_name, row.usdt_amount, row.user_id) for row in result.all()]

    def _to_entity(self, db_user: MyMtlWalletBotUsers) -> User:
        from typing import cast
        return User(
            id=cast(int, db_user.user_id),
            username=db_user.user_name,
            language=str(db_user.lang or 'en'),
            default_address=db_user.default_address,
            can_5000=int(db_user.can_5000 or 0)
        )
