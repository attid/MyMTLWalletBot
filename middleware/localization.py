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
        data["l10n"] = self.localization_service
        return await handler(event, data)
