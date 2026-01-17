"""SQLAlchemy implementation of IChequeRepository."""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from core.domain.entities import Cheque
from core.interfaces.repositories import IChequeRepository
from db.models import MyMtlWalletBotCheque, MyMtlWalletBotChequeHistory, ChequeStatus


class SqlAlchemyChequeRepository(IChequeRepository):
    """SQLAlchemy implementation for cheque operations."""
    
    def __init__(self, session: Session):
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
        self.session.commit()
        return self._to_entity(db_cheque)
    
    async def get_by_uuid(self, uuid: str, user_id: int = None) -> Optional[Cheque]:
        """Get a cheque by UUID."""
        stmt = select(MyMtlWalletBotCheque).where(MyMtlWalletBotCheque.cheque_uuid == uuid)
        if user_id is not None:
            stmt = stmt.where(MyMtlWalletBotCheque.user_id == user_id)
        result = self.session.execute(stmt)
        db_cheque = result.scalar_one_or_none()
        if db_cheque:
            return self._to_entity(db_cheque)
        return None
    
    async def get_receive_count(self, uuid: str, user_id: int = None) -> int:
        """Get the number of times a cheque has been received."""
        query = self.session.query(func.count('*')). \
            select_from(MyMtlWalletBotCheque). \
            join(MyMtlWalletBotChequeHistory, MyMtlWalletBotCheque.cheque_id == MyMtlWalletBotChequeHistory.cheque_id). \
            filter(MyMtlWalletBotCheque.cheque_uuid == uuid)
        
        if user_id is not None:
            query = query.filter(MyMtlWalletBotChequeHistory.user_id == user_id)
        
        receive_count = query.scalar()
        return receive_count or 0
    
    async def get_available(self, user_id: int) -> List[Cheque]:
        """Get all available (not fully claimed) cheques for a user."""
        cheques = self.session.query(
            MyMtlWalletBotCheque
        ).outerjoin(
            MyMtlWalletBotChequeHistory,
            MyMtlWalletBotCheque.cheque_id == MyMtlWalletBotChequeHistory.cheque_id
        ).group_by(
            MyMtlWalletBotCheque
        ).having(
            func.count(MyMtlWalletBotChequeHistory.cheque_id) < MyMtlWalletBotCheque.cheque_count
        ).filter(
            MyMtlWalletBotCheque.user_id == user_id,
            MyMtlWalletBotCheque.cheque_status != ChequeStatus.CANCELED.value
        ).all()
        
        return [self._to_entity(cheque) for cheque in cheques]
    
    async def add_history(self, cheque_id: int, user_id: int) -> None:
        """Record a cheque claim in history."""
        new_history = MyMtlWalletBotChequeHistory(
            user_id=user_id,
            dt_block=datetime.now(),
            cheque_id=cheque_id
        )
        self.session.add(new_history)
        self.session.commit()
    
    def _to_entity(self, db_cheque: MyMtlWalletBotCheque) -> Cheque:
        return Cheque(
            id=db_cheque.cheque_id,
            uuid=db_cheque.cheque_uuid,
            user_id=db_cheque.user_id,
            amount=db_cheque.cheque_amount,
            count=db_cheque.cheque_count,
            comment=db_cheque.cheque_comment,
            status=db_cheque.cheque_status
        )
