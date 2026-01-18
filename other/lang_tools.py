from typing import Union
from aiogram import types
from infrastructure.services.app_context import AppContext
from sqlalchemy.orm import Session

from db.models import MyMtlWalletBotUsers
from infrastructure.utils.common_utils import get_user_id
from other.global_data import global_data


def change_user_lang(session: Session, user_id: int, lang: str):
    # Direct DB update (legacy pattern, should use repo)
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        user.lang = lang
        session.commit()
        
        # Update cache in service
        if global_data.localization_service:
            global_data.localization_service.set_user_language(user_id, lang)
        else:
             # Fallback to legacy dictionary if service missing (should not happen)
             global_data.user_lang_dic[user_id] = lang
    else:
        raise ValueError(f"No user found with user_id {user_id}")


def check_user_lang(session: Session, user_id: int):
    if global_data.localization_service:
        return global_data.localization_service.get_user_language(user_id)
    
    # Fallback legacy
    user = session.query(MyMtlWalletBotUsers.lang).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        return user.lang
    else:
        return None


def my_gettext(user_id: Union[types.CallbackQuery, types.Message, int, str], text: str, param: tuple = (), app_context: AppContext = None) -> str:
    # Resolve service
    service = None
    if app_context and app_context.localization_service:
        service = app_context.localization_service
    elif global_data.localization_service:
        service = global_data.localization_service
        
    if service:
        return service.get_text(user_id, text, param)
    
    # Critical fallback if no service available (e.g. tests without setup)
    # Using simple return or limited logic
    return f"{text} (no_loc)"


def check_user_id(session: Session, user_id: int):
    user_count = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).count()
    return user_count > 0
