from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import select, update, and_
from core.interfaces.repositories import IMessageRepository
from db.models import MyMtlWalletBotMessages

class SqlAlchemyMessageRepository(IMessageRepository):
    def __init__(self, session: Session):
        self.session = session

    async def enqueue(self, user_id: int, text: str, use_alarm: int = 0, update_id: int = None, button_json: str = None) -> None:
        new_message = MyMtlWalletBotMessages(
            user_id=user_id, 
            user_message=text,
            was_send=0
        )
        self.session.add(new_message)
        self.session.commit()

    async def get_unsent(self, limit: int = 10) -> List[MyMtlWalletBotMessages]:
        stmt = select(MyMtlWalletBotMessages).where(MyMtlWalletBotMessages.was_send == 0).limit(limit)
        result = self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def mark_sent(self, message_id: int) -> None:
        stmt = update(MyMtlWalletBotMessages).where(
            MyMtlWalletBotMessages.message_id == message_id
        ).values(was_send=1)
        self.session.execute(stmt)
        self.session.commit()
        
    async def mark_failed(self, message_id: int) -> None:
        # Mark as 2 (failed/retry later?)
        stmt = update(MyMtlWalletBotMessages).where(
            MyMtlWalletBotMessages.message_id == message_id
        ).values(was_send=2)
        self.session.execute(stmt)
        self.session.commit()
