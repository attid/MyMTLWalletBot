from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from core.interfaces.repositories import INotificationRepository
from db.models import MyMtlWalletBotUsers, NotificationFilter


DEFAULT_XLM_FILTER_ASSET = "XLM"
DEFAULT_XLM_FILTER_MIN_AMOUNT = 0.1
DEFAULT_XLM_FILTER_OPERATION = "payment"


class SqlAlchemyNotificationRepository(INotificationRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> List[NotificationFilter]:
        stmt = select(NotificationFilter).where(NotificationFilter.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        user_id: int,
        public_key: Optional[str],
        asset_code: Optional[str],
        min_amount: float,
        operation_type: str,
    ) -> NotificationFilter:
        new_filter = NotificationFilter(
            user_id=user_id,
            public_key=public_key,
            asset_code=asset_code,
            min_amount=float(min_amount),  # type: ignore
            operation_type=operation_type,
        )
        self.session.add(new_filter)
        await self.session.commit()
        return new_filter

    async def delete_all_by_user(self, user_id: int) -> None:
        stmt = delete(NotificationFilter).where(NotificationFilter.user_id == user_id)
        await self.session.execute(stmt)
        await self.session.commit()

    async def find_duplicate(
        self,
        user_id: int,
        public_key: Optional[str],
        asset_code: Optional[str],
        min_amount: float,
        operation_type: str,
    ) -> Optional[NotificationFilter]:
        stmt = (
            select(NotificationFilter)
            .where(NotificationFilter.user_id == user_id)
            .where(NotificationFilter.public_key == public_key)
            .where(NotificationFilter.asset_code == asset_code)
            .where(NotificationFilter.min_amount == min_amount)
            .where(NotificationFilter.operation_type == operation_type)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, filter_id: int) -> Optional[NotificationFilter]:
        stmt = select(NotificationFilter).where(NotificationFilter.id == filter_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_by_id(self, filter_id: int, user_id: int) -> bool:
        """Delete a filter by ID with owner verification."""
        stmt = delete(NotificationFilter).where(
            NotificationFilter.id == filter_id, NotificationFilter.user_id == user_id
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0  # type: ignore

    async def ensure_default_xlm_filter(self, user_id: int) -> bool:
        existing_filter = await self.find_duplicate(
            user_id=user_id,
            public_key=None,
            asset_code=DEFAULT_XLM_FILTER_ASSET,
            min_amount=DEFAULT_XLM_FILTER_MIN_AMOUNT,
            operation_type=DEFAULT_XLM_FILTER_OPERATION,
        )
        if existing_filter:
            return False

        await self.create(
            user_id=user_id,
            public_key=None,
            asset_code=DEFAULT_XLM_FILTER_ASSET,
            min_amount=DEFAULT_XLM_FILTER_MIN_AMOUNT,
            operation_type=DEFAULT_XLM_FILTER_OPERATION,
        )
        return True

    async def backfill_default_xlm_filters(self) -> int:
        user_result = await self.session.execute(select(MyMtlWalletBotUsers.user_id))
        user_ids = [int(row[0]) for row in user_result.all()]

        created_count = 0
        for user_id in user_ids:
            existing_filter = await self.find_duplicate(
                user_id=user_id,
                public_key=None,
                asset_code=DEFAULT_XLM_FILTER_ASSET,
                min_amount=DEFAULT_XLM_FILTER_MIN_AMOUNT,
                operation_type=DEFAULT_XLM_FILTER_OPERATION,
            )
            if existing_filter:
                continue

            self.session.add(
                NotificationFilter(
                    user_id=user_id,
                    public_key=None,
                    asset_code=DEFAULT_XLM_FILTER_ASSET,
                    min_amount=DEFAULT_XLM_FILTER_MIN_AMOUNT,
                    operation_type=DEFAULT_XLM_FILTER_OPERATION,
                )
            )
            created_count += 1

        await self.session.commit()
        return created_count
