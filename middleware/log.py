import asyncio
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from loguru import logger
from db.models import MyMtlWalletBotLog
# from other.global_data import global_data, LogQuery
# LogQuery should be moved, but for now assuming it's still there or imported from new location if moved.
# The plan said "Move LogQuery to infrastructure/models.py". I haven't done that yet.
# I will keep importing from global_data for now but will prepare for removal.
from other.global_data import global_data 
from infrastructure.log_models import LogQuery 
from other.loguru_tools import safe_catch_async
from infrastructure.services.app_context import AppContext


class LogButtonClickCallbackMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:
        app_context: AppContext = data.get("app_context")
        if app_context:
            app_context.log_queue.put_nowait(LogQuery(
                user_id=event.from_user.id,
                log_operation='callback',
                log_operation_info=event.data.split(':')[0]
            ))
        else:
            # Fallback while migrating or if middleware order is wrong
            global_data.log_queue.put_nowait(LogQuery(
                user_id=event.from_user.id,
                log_operation='callback',
                log_operation_info=event.data.split(':')[0]
            ))
            
        return await handler(event, data)


#

from sqlalchemy.exc import SQLAlchemyError
@safe_catch_async
async def log_worker(app_context: AppContext):
    while True:  # not queue.empty():
        log_item: LogQuery = await app_context.log_queue.get()
        try:
            new_log = MyMtlWalletBotLog(
                user_id=log_item.user_id,
                log_dt=log_item.log_dt,
                log_operation=log_item.log_operation[:32],
                log_operation_info=log_item.log_operation_info[:32]
            )
            with app_context.db_pool.get_session() as session:
                session.add(new_log)
                session.commit()
        except Exception as e:
            logger.warning(f'{log_item.user_id}-{log_item.log_operation} failed {type(e)}')
        app_context.log_queue.task_done()
        await asyncio.sleep(1)
