from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from core.interfaces.repositories import IMessageRepository
from db.models import MyMtlWalletBotMessages

class SqlAlchemyMessageRepository(IMessageRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def enqueue(self, user_id: int, text: str, use_alarm: int = 0, update_id: Optional[int] = None, button_json: Optional[str] = None) -> None:
        new_message = MyMtlWalletBotMessages(
            user_id=user_id, 
            user_message=text,
            was_send=0
        )
        self.session.add(new_message)
        await self.session.commit()

    async def get_unsent(self, limit: int = 10) -> List[MyMtlWalletBotMessages]:
        stmt = select(MyMtlWalletBotMessages).where(MyMtlWalletBotMessages.was_send == 0).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def mark_sent(self, message_id: int) -> None:
        stmt = update(MyMtlWalletBotMessages).where(
            MyMtlWalletBotMessages.message_id == message_id
        ).values(was_send=1)
        await self.session.execute(stmt)
        await self.session.commit()
        
    async def mark_failed(self, message_id: int) -> None:
        # Mark as 2 (failed/retry later?)
        stmt = update(MyMtlWalletBotMessages).where(
            MyMtlWalletBotMessages.message_id == message_id
        ).values(was_send=2)
        await self.session.execute(stmt)
        await self.session.commit()
