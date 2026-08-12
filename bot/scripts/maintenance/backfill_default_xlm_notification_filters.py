"""One-time backfill for the default XLM dust notification filter."""

from __future__ import annotations

import asyncio
import os
import sys

from loguru import logger

# Add bot package root for direct script execution from this nested directory.
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from db.db_pool import db_pool
from infrastructure.persistence.sqlalchemy_notification_repository import (
    SqlAlchemyNotificationRepository,
)


async def backfill_default_xlm_notification_filters() -> int:
    async with db_pool.get_session() as session:
        repo = SqlAlchemyNotificationRepository(session)
        return await repo.backfill_default_xlm_filters()


async def main() -> int:
    created_count = await backfill_default_xlm_notification_filters()
    logger.info("Default XLM notification filters created: {}", created_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
