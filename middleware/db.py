from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject

from db.requests import get_user_lang


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool):
        super().__init__()
        self.session_pool = session_pool

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        fsm: FSMContext = data["state"]
        fsm_data = await fsm.get_data()
        if fsm_data.get('user_lang', None) is None:
            # i think there nothing change if will be new data
            await fsm.update_data(
                show_more=fsm_data.get('show_more', False),
                user_name=fsm_data.get('user_name', ''),
                user_id=fsm_data.get('user_id', event.from_user.id),
                last_message_id=data.get('last_message_id', 0)
            )
            with self.session_pool.get_session() as session:
                await fsm.update_data(
                    user_lang=fsm_data.get('user_lang', get_user_lang(session, event.from_user.id))
                )
        with self.session_pool.get_session() as session:
            data["session"] = session
            return await handler(event, data)
