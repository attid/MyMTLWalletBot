import asyncio
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from loguru import logger
from db.models import MyMtlWalletBotLog
from utils.global_data import global_data, LogQuery


class LogButtonClickCallbackMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:
        global_data.log_queue.put_nowait(LogQuery(
            user_id=event.from_user.id,
            log_operation='callback',
            log_operation_info=event.data.split(':')[0]
        ))
        return await handler(event, data)


#

from sqlalchemy.exc import SQLAlchemyError

async def log_worker(session_pool):
    while True:  # not queue.empty():
        log_item: LogQuery = await global_data.log_queue.get()
        try:
            new_log = MyMtlWalletBotLog(
                user_id=log_item.user_id,
                log_dt=log_item.log_dt,
                log_operation=log_item.log_operation[:32],
                log_operation_info=log_item.log_operation_info[:32]
            )
            with session_pool() as session:
                session.add(new_log)
                session.commit()
        except SQLAlchemyError as e:
            logger.warning(f'{log_item.user_id}-{log_item.log_operation} failed {type(e)}')
        global_data.log_queue.task_done()
        await asyncio.sleep(1)
