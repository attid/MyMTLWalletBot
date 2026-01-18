from aiogram import Dispatcher
from aiogram.fsm.storage.base import StorageKey
from loguru import logger

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
    with session_pool.get_session() as session:
        msg_repo = SqlAlchemyMessageRepository(session)
        # Using repo unsent messages
        messages = await msg_repo.get_unsent(10)
        for message in messages:
            try:
                await cmd_info_message(session, message.user_id, message.user_message, None, app_context=app_context)
            except Exception as ex:
                if session.query(MyMtlWalletBotMessages).filter_by(message_id=message.message_id).first():
                    await msg_repo.mark_failed(message.message_id)
                logger.info(['cmd_send_message_1m', ex])
            fsm_storage_key = StorageKey(bot_id=app_context.bot.id, user_id=message.user_id, chat_id=message.user_id)
            await app_context.dispatcher.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})
            
            await msg_repo.mark_sent(message.message_id)
