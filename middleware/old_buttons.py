from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from utils.lang_utils import get_last_message_id


class CheckOldButtonCallbackMiddleware(BaseMiddleware):
    def __init__(self, session):
        super().__init__()
        self.session = session

    async def __call__(
            self,
            handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:
        last_message_id = get_last_message_id(self.session, event.from_user.id)
        # logger.info(['good_id', last_message_id])
        if event.message.message_id == last_message_id:
            return await handler(event, data)
        elif last_message_id == 0:
            return await handler(event, data)
        elif event.message.reply_markup.__str__().find('cheque_callback_') > 0:
            return await handler(event, data)
        else:
            await event.answer(
                "Old button =(",
                show_alert=True
            )
            await event.message.edit_reply_markup(reply_markup=None)
            return
