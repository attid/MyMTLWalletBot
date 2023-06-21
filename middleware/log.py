import asyncio
from datetime import datetime
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from loguru import logger

import fb
from utils.aiogram_utils import log_queue, LogQuery
from utils.lang_utils import get_last_message_id


class LogButtonClickCallbackMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:
        log_queue.put_nowait(LogQuery(
            user_id=event.from_user.id,
            log_operation='callback',
            log_operation_info=event.data.split(':')[0]
        ))
        return await handler(event, data)


#

async def log_worker():
    while True:  # not queue.empty():
        log_item: LogQuery = await log_queue.get()
        try:
            fb.execsql('insert into mymtlwalletbot_log (user_id, log_dt, log_operation, log_operation_info) '
                       'values (?, ?, ?, ?)',
                       (log_item.user_id, log_item.log_dt, log_item.log_operation[:32], log_item.log_operation_info[:32]))

        except Exception as e:
            logger.warning(f' {log_item.user_id}-{log_item.log_operation} failed {type(e)}')
        log_queue.task_done()
        await asyncio.sleep(1)
