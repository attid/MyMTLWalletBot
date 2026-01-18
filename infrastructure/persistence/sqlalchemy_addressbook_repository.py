"""SQLAlchemy implementation of IAddressBookRepository."""
from typing import List, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities import AddressBookEntry
from core.interfaces.repositories import IAddressBookRepository
from db.models import MyMtlWalletBotBook


class SqlAlchemyAddressBookRepository(IAddressBookRepository):
    """SQLAlchemy implementation for address book operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_all(self, user_id: int) -> List[AddressBookEntry]:
        """Get all address book entries for a user."""
        stmt = select(MyMtlWalletBotBook).where(MyMtlWalletBotBook.user_id == user_id)
        result = await self.session.execute(stmt)
        db_entries = result.scalars().all()
        return [self._to_entity(entry) for entry in db_entries]
    
    async def get_by_id(self, entry_id: int, user_id: int) -> Optional[AddressBookEntry]:
        """Get a specific address book entry."""
        stmt = select(MyMtlWalletBotBook).where(
            MyMtlWalletBotBook.id == entry_id,
            MyMtlWalletBotBook.user_id == user_id
        )
        result = await self.session.execute(stmt)
        db_entry = result.scalar_one_or_none()
        if db_entry:
            return self._to_entity(db_entry)
        return None
    
    async def create(self, user_id: int, address: str, name: str) -> AddressBookEntry:
        """Create a new address book entry."""
        db_entry = MyMtlWalletBotBook(
            user_id=user_id,
            address=address[:64],
            name=name[:64]
        )
        self.session.add(db_entry)
        await self.session.commit()
        return self._to_entity(db_entry)
    
    async def delete(self, entry_id: int, user_id: int) -> None:
        """Delete an address book entry."""
        stmt = select(MyMtlWalletBotBook).where(
            MyMtlWalletBotBook.id == entry_id,
            MyMtlWalletBotBook.user_id == user_id
        )
        result = await self.session.execute(stmt)
        db_entry = result.scalar_one_or_none()
        if db_entry:
            await self.session.delete(db_entry)
            await self.session.commit()
    
    def _to_entity(self, db_entry: MyMtlWalletBotBook) -> AddressBookEntry:
        return AddressBookEntry(
            id=db_entry.id,
            user_id=db_entry.user_id,
            address=db_entry.address,
            name=db_entry.name
        )
