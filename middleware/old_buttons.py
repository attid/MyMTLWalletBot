from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery


class CheckOldButtonCallbackMiddleware(BaseMiddleware):
    def __init__(self, session_pool):
        super().__init__()
        self.session_pool = session_pool

    async def __call__(
            self,
            handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:
        fsm: FSMContext = data["state"]
        fsm_data = await fsm.get_data()
        last_message_id = fsm_data.get('last_message_id', 0)
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
