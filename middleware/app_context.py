from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from infrastructure.services.app_context import AppContext

class AppContextMiddleware(BaseMiddleware):
    def __init__(self, app_context: AppContext):
        super().__init__()
        self.app_context = app_context

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        data["app_context"] = self.app_context
        return await handler(event, data)
