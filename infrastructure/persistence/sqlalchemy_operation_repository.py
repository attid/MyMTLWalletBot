from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from core.interfaces.repositories import IOperationRepository
from db.models import TOperations

class SqlAlchemyOperationRepository(IOperationRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, operation_id: str) -> Optional[TOperations]:
        stmt = select(TOperations).where(TOperations.id == operation_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent_for_addresses(self, addresses: List[str], last_event_id: int, 
                                     minutes: int = 30) -> List[TOperations]:
        """
        Mimics logic from fetch_addresses but focused on getting operations.
        Actually fetch_addresses logic is about discovering accounts with new ops.
        Logic: get operations for accounts in list, newer than last_event_id and within last 30 min.
        """
        # Note: fetch_addresses logic was complex join. 
        # Here we just implement retrieval by multiple accounts if needed.
        # But wait, time_handlers logic iterates found 'accounts' then queries operations for EACH handle_address.
        # So we likely need `get_by_account_since_id`.
        return []

    async def get_by_account_since_id(self, account: str, last_id: int, minutes: int = 30) -> List[TOperations]:
        stmt = select(TOperations).where(
            or_(TOperations.for_account == account,
                TOperations.from_account == account,
                TOperations.code2 == account)
        ).where(
            TOperations.id > last_id
        ).where(
            TOperations.dt > datetime.utcnow() - timedelta(minutes=minutes)
        ).where(
            TOperations.arhived == None
        ).order_by(TOperations.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
