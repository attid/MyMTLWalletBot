from aiogram import Dispatcher
from aiogram.fsm.storage.base import StorageKey
from loguru import logger

from sqlalchemy import select
from db.models import MyMtlWalletBotMessages
from db.db_pool import DatabasePool
from infrastructure.persistence.sqlalchemy_message_repository import SqlAlchemyMessageRepository
from infrastructure.utils.async_utils import with_timeout
from infrastructure.services.app_context import AppContext
from other.loguru_tools import safe_catch_async
from routers.start_msg import cmd_info_message

@with_timeout(60)
@safe_catch_async
async def cmd_send_message_1m(session_pool: DatabasePool, app_context: AppContext):
    async with session_pool.get_session() as session:
        msg_repo = SqlAlchemyMessageRepository(session)
        # Using repo unsent messages
        messages = await msg_repo.get_unsent(10)
        for message in messages:
            try:
                assert message.user_id is not None, "user_id must not be None"
                assert message.user_message is not None, "user_message must not be None"
                await cmd_info_message(session, message.user_id, message.user_message, None, app_context=app_context)
            except Exception as ex:
                # Check if message still exists
                stmt = select(MyMtlWalletBotMessages).where(MyMtlWalletBotMessages.message_id == message.message_id)
                result = await session.execute(stmt)
                if result.scalar_one_or_none():
                    assert message.message_id is not None, "message_id must not be None"
                    await msg_repo.mark_failed(message.message_id)
                logger.info(['cmd_send_message_1m', ex])
            assert message.user_id is not None, "user_id must not be None"
            assert message.message_id is not None, "message_id must not be None"
            dispatcher = app_context.dispatcher
            assert dispatcher is not None, "Dispatcher must be initialized in app_context"
            fsm_storage_key = StorageKey(bot_id=app_context.bot.id, user_id=message.user_id, chat_id=message.user_id)
            await dispatcher.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})

            await msg_repo.mark_sent(message.message_id)
