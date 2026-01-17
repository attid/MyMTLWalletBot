from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject

from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository

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
                user_repo = SqlAlchemyUserRepository(session)
                user = await user_repo.get_by_id(event.from_user.id)
                lang = user.language if user else 'en'
                
                await fsm.update_data(
                    user_lang=fsm_data.get('user_lang', lang)
                )
        with self.session_pool.get_session() as session:
            data["session"] = session
            return await handler(event, data)
