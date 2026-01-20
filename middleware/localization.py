from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from infrastructure.services.localization_service import LocalizationService

class LocalizationMiddleware(BaseMiddleware):
    def __init__(self, localization_service: LocalizationService):
        super().__init__()
        self.localization_service = localization_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Helper to get user_id from various event types
        user_id = 0
        if hasattr(event, "from_user") and event.from_user:
            user_id = event.from_user.id
        elif hasattr(event, "chat") and event.chat:
            user_id = event.chat.id
        # Alternatively use common util if object structure allows, but event is TelegramObject
        # which might be Update, Message, CallbackQuery etc.
        # AIogram 3.x middlewares usually receive specific event types if registered so, 
        # or Update if outer. Assuming standard message/callback/update.
        
        # Try to use common utility if applicable, or safe attribute access
        try:
           from aiogram.types import Message, CallbackQuery
           from infrastructure.utils.common_utils import get_user_id
           if isinstance(event, (Message, CallbackQuery)):
               user_id = get_user_id(event)
        except:
           pass

        if isinstance(user_id, int) and user_id > 0:
            await self.localization_service.get_user_language_async(user_id)

        data["l10n"] = self.localization_service
        return await handler(event, data)
