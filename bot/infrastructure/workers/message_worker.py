from dataclasses import dataclass

from aiogram.fsm.storage.base import StorageKey
from loguru import logger

from infrastructure.persistence.sqlalchemy_message_repository import (
    SqlAlchemyMessageRepository,
)
from infrastructure.utils.async_utils import with_timeout
from infrastructure.services.app_context import AppContext
from other.loguru_tools import safe_catch_async
from routers.start_msg import cmd_info_message


@dataclass(frozen=True)
class QueuedMessage:
    message_id: int
    user_id: int
    user_message: str


@with_timeout(60)
@safe_catch_async
async def cmd_send_message_1m(app_context: AppContext):
    health_service = getattr(app_context, "bot_health_service", None)
    if health_service is not None:
        health_service.mark_scheduler_started()
    try:
        async with app_context.db_pool.get_session() as session:
            msg_repo = SqlAlchemyMessageRepository(session)
            rows = await msg_repo.get_unsent(10)
            messages = []
            for row in rows:
                assert row.message_id is not None, "message_id must not be None"
                assert row.user_id is not None, "user_id must not be None"
                assert row.user_message is not None, "user_message must not be None"
                messages.append(
                    QueuedMessage(
                        message_id=row.message_id,
                        user_id=row.user_id,
                        user_message=row.user_message,
                    )
                )

        for message in messages:
            try:
                await cmd_info_message(
                    None,
                    message.user_id,
                    message.user_message,
                    None,
                    app_context=app_context,
                )
                dispatcher = app_context.dispatcher
                assert dispatcher is not None, (
                    "Dispatcher must be initialized in app_context"
                )
                fsm_storage_key = StorageKey(
                    bot_id=app_context.bot.id,
                    user_id=message.user_id,
                    chat_id=message.user_id,
                )
                await dispatcher.storage.update_data(
                    key=fsm_storage_key, data={"last_message_id": 0}
                )
            except Exception as ex:
                async with app_context.db_pool.get_session() as session:
                    msg_repo = SqlAlchemyMessageRepository(session)
                    await msg_repo.mark_failed(message.message_id)
                logger.info(["cmd_send_message_1m", ex])
                continue

            async with app_context.db_pool.get_session() as session:
                msg_repo = SqlAlchemyMessageRepository(session)
                await msg_repo.mark_sent(message.message_id)
    finally:
        if health_service is not None:
            health_service.mark_scheduler_completed()
