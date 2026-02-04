"""SQLAlchemy implementation of IChequeRepository."""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities import Cheque
from core.interfaces.repositories import IChequeRepository
from db.models import MyMtlWalletBotCheque, MyMtlWalletBotChequeHistory, ChequeStatus


class SqlAlchemyChequeRepository(IChequeRepository):
    """SQLAlchemy implementation for cheque operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, uuid: str, amount: str, count: int, user_id: int, comment: str) -> Cheque:
        """Create a new cheque."""
        db_cheque = MyMtlWalletBotCheque(
            cheque_uuid=uuid,
            cheque_amount=amount,
            cheque_count=count,
            user_id=user_id,
            cheque_comment=comment
        )
        self.session.add(db_cheque)
        await self.session.commit()
        return self._to_entity(db_cheque)
    
    async def get_by_uuid(self, uuid: str, user_id: Optional[int] = None) -> Optional[Cheque]:
        """Get a cheque by UUID."""
        stmt = select(MyMtlWalletBotCheque).where(MyMtlWalletBotCheque.cheque_uuid == uuid)
        if user_id is not None:
            stmt = stmt.where(MyMtlWalletBotCheque.user_id == user_id)
        result = await self.session.execute(stmt)
        db_cheque = result.scalar_one_or_none()
        if db_cheque:
            return self._to_entity(db_cheque)
        return None
    
    async def get_receive_count(self, uuid: str, user_id: Optional[int] = None) -> int:
        """Get the number of times a cheque has been received."""
        # Using future-style select with join and count
        stmt = select(func.count('*')).select_from(MyMtlWalletBotCheque).join(
            MyMtlWalletBotChequeHistory, 
            MyMtlWalletBotCheque.cheque_id == MyMtlWalletBotChequeHistory.cheque_id
        ).where(MyMtlWalletBotCheque.cheque_uuid == uuid)
        
        if user_id is not None:
            stmt = stmt.where(MyMtlWalletBotChequeHistory.user_id == user_id)
        
        result = await self.session.execute(stmt)
        receive_count = result.scalar()
        return int(receive_count or 0)
    
    async def get_available(self, user_id: int) -> List[Cheque]:
        """Get all available (not fully claimed) cheques for a user."""
        # 1. Find IDs of cheques that are not fully claimed
        # We group by cheque_id (PK) and cheque_count (needed for HAVING)
        subq = select(MyMtlWalletBotCheque.cheque_id).outerjoin(
            MyMtlWalletBotChequeHistory,
            MyMtlWalletBotCheque.cheque_id == MyMtlWalletBotChequeHistory.cheque_id
        ).where(
            MyMtlWalletBotCheque.user_id == user_id
        ).where(
            MyMtlWalletBotCheque.cheque_status != ChequeStatus.CANCELED.value
        ).group_by(
            MyMtlWalletBotCheque.cheque_id,
            MyMtlWalletBotCheque.cheque_count
        ).having(
            func.count(MyMtlWalletBotChequeHistory.cheque_id) < MyMtlWalletBotCheque.cheque_count
        )
        
        # 2. Fetch the full cheque entities for these IDs
        stmt = select(MyMtlWalletBotCheque).where(
            MyMtlWalletBotCheque.cheque_id.in_(subq)
        )
        
        result = await self.session.execute(stmt)
        cheques = result.scalars().all()
        
        return [self._to_entity(cheque) for cheque in cheques]
    
    async def add_history(self, cheque_id: int, user_id: int) -> None:
        """Record a cheque claim in history."""
        new_history = MyMtlWalletBotChequeHistory(
            user_id=user_id,
            dt_block=datetime.now(),
            cheque_id=cheque_id
        )
        self.session.add(new_history)
        await self.session.commit()
    
    async def cancel(self, cheque_uuid: str, user_id: int) -> bool:
        """Cancel a cheque (set status to CANCELED)."""
        stmt = select(MyMtlWalletBotCheque).where(
             MyMtlWalletBotCheque.cheque_uuid == cheque_uuid
        ).where(
             MyMtlWalletBotCheque.user_id == user_id
        )
        result = await self.session.execute(stmt)
        db_cheque = result.scalar_one_or_none()
        if db_cheque:
            db_cheque.cheque_status = ChequeStatus.CANCELED.value
            await self.session.commit()
            return True
        return False

    
    def _to_entity(self, db_cheque: MyMtlWalletBotCheque) -> Cheque:
        from typing import cast
        return Cheque(
            id=cast(int, db_cheque.cheque_id),
            uuid=cast(str, db_cheque.cheque_uuid),
            user_id=cast(int, db_cheque.user_id),
            amount=cast(str, db_cheque.cheque_amount),
            count=cast(int, db_cheque.cheque_count),
            comment=db_cheque.cheque_comment,
            status=cast(int, db_cheque.cheque_status)
        )
