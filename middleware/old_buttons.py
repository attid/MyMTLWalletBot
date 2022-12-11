from datetime import datetime
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery

from app_logger import logger
from utils.lang_utils import get_last_message_id


# # Это будет inner-мидлварь на сообщения
# class TestMessageMiddleware(BaseMiddleware):
#     async def __call__(
#             self,
#             handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
#             event: Message,
#             data: Dict[str, Any]
#     ) -> Any:
#         # Если сегодня не суббота и не воскресенье,
#         # то продолжаем обработку.
#         if data.get('re'):
#             return await handler(event, data)
#         # В противном случае просто вернётся None
#         # и обработка прекратится


class CheckOldButtonCallbackMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:
        last_message_id = get_last_message_id(event.from_user.id)
        #logger.info(['good_id', last_message_id])
        if event.message.message_id == last_message_id:
            return await handler(event, data)
        elif last_message_id == 0:
            return await handler(event, data)
        else:
            await event.answer(
                "Old button =(",
                show_alert=True
            )
            await event.message.edit_reply_markup(reply_markup=None)
            return
