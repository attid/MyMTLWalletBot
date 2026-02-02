from typing import Union, Optional, Any
from aiogram import types
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import MyMtlWalletBotUsers
from infrastructure.services.app_context import AppContext
from loguru import logger

from sqlalchemy import select

async def change_user_lang(session: AsyncSession, user_id: int, lang: str):
    # Direct DB update (legacy pattern, should use repo)
    stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user is not None:
        user.lang = lang
        await session.commit()
    else:
        raise ValueError(f"No user found with user_id {user_id}")


def get_user_id(message: Union[types.Message, types.CallbackQuery, int]) -> int:
    if isinstance(message, int):
        return message
    if isinstance(message, (types.Message, types.CallbackQuery)):
        if message.from_user:
            return message.from_user.id
    if hasattr(message, 'chat') and getattr(message, 'chat'):
        return getattr(message, 'chat').id
    return 0


async def check_user_lang(session: AsyncSession, user_id: int):
    # Fallback legacy
    stmt = select(MyMtlWalletBotUsers.lang).where(MyMtlWalletBotUsers.user_id == user_id)
    result = await session.execute(stmt)
    lang = result.scalar_one_or_none()
    return lang



def my_gettext(user_id: Union[types.CallbackQuery, types.Message, int], text: str, param: tuple = (), *,
               app_context: Optional[AppContext] = None, localization_service: Any = None) -> str:
    # Resolve service
    service = localization_service
    if not service and app_context and app_context.localization_service:
        service = app_context.localization_service
        
    if service:
        try:
             # Check if service has get_text method
             if hasattr(service, 'get_text'):
                 return service.get_text(get_user_id(user_id), text, param)
        except Exception as e:
             logger.error(f"Error in my_gettext: {e}")
    
    # Critical fallback if no service available (e.g. tests without setup)
    # Using simple return or limited logic
    return f"{text} (no_loc)"


async def check_user_id(session: AsyncSession, user_id: int):
    stmt = select(MyMtlWalletBotUsers).where(MyMtlWalletBotUsers.user_id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    return user is not None
