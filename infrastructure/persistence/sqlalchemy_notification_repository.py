from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from core.interfaces.repositories import INotificationRepository
from db.models import NotificationFilter

class SqlAlchemyNotificationRepository(INotificationRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> List[NotificationFilter]:
        stmt = select(NotificationFilter).where(NotificationFilter.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, user_id: int, public_key: Optional[str], asset_code: Optional[str], 
                    min_amount: float, operation_type: str) -> NotificationFilter:
        new_filter = NotificationFilter(
            user_id=user_id,
            public_key=public_key,
            asset_code=asset_code,
            min_amount=float(min_amount),  # type: ignore
            operation_type=operation_type
        )
        self.session.add(new_filter)
        await self.session.commit()
        return new_filter

    async def delete_all_by_user(self, user_id: int) -> None:
        stmt = delete(NotificationFilter).where(NotificationFilter.user_id == user_id)
        await self.session.execute(stmt)
        await self.session.commit()

    async def find_duplicate(self, user_id: int, public_key: Optional[str], asset_code: Optional[str], 
                           min_amount: float, operation_type: str) -> Optional[NotificationFilter]:
        stmt = select(NotificationFilter).where(
            NotificationFilter.user_id == user_id
        ).where(
            NotificationFilter.public_key == public_key
        ).where(
            NotificationFilter.asset_code == asset_code
        ).where(
            NotificationFilter.min_amount == min_amount
        ).where(
            NotificationFilter.operation_type == operation_type
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
