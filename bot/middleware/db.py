from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject

from infrastructure.services.localization_service import LocalizationService
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool, localization_service: LocalizationService):
        super().__init__()
        self.session_pool = session_pool
        self.localization_service = localization_service

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        from_user = getattr(event, 'from_user', None)
        if not from_user:
            async with self.session_pool.get_session() as session:
                data["session"] = session
                return await handler(event, data)

        fsm: FSMContext = data["state"]
        fsm_data = await fsm.get_data()
        if fsm_data.get('user_lang', None) is None:
            # i think there nothing change if will be new data
            await fsm.update_data(
                show_more=fsm_data.get('show_more', False),
                user_name=fsm_data.get('user_name', ''),
                user_id=fsm_data.get('user_id', from_user.id),
                last_message_id=data.get('last_message_id', 0)
            )
            async with self.session_pool.get_session() as session:
                user_repo = SqlAlchemyUserRepository(session)
                user = await user_repo.get_by_id(from_user.id)
                lang = user.language if user else 'en'
                
                # Update LocalizationService cache
                self.localization_service.set_user_language(from_user.id, lang)

                await fsm.update_data(
                    user_lang=fsm_data.get('user_lang', lang)
                )
        else:
            # If lang is in FSM, ensure it's in service cache too (in case service restarted or cache cleared)
            # Or just set it blindly to be safe and fast.
            lang = fsm_data.get('user_lang', 'en')
            self.localization_service.set_user_language(from_user.id, lang)
        async with self.session_pool.get_session() as session:
            data["session"] = session
            return await handler(event, data)
