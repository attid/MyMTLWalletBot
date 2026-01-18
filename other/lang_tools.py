import json
from os import listdir
from typing import Union
from aiogram import types
from infrastructure.services.app_context import AppContext
from sqlalchemy.orm import Session

from other.config_reader import start_path
from db.models import MyMtlWalletBotUsers
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from infrastructure.utils.common_utils import get_user_id
from other.global_data import global_data

for file in listdir(f"{start_path}/langs/"):
    if file.endswith(".json"):
        with open(f"{start_path}/langs/" + file, "r") as fp:
            #print(f"{start_path}/langs/" + file)
            global_data.lang_dict[file.split('.')[0]] = json.load(fp)


def change_user_lang(session: Session, user_id: int, lang: str):

    # Ideally should use repo.update but we have partial update here
    # Since we are inside legacy tool, explicit update is fine or use repo.
    # We used User entity in repo. 
    # Let's use repo if we have method.
    # IUserRepository has update(user: User).
    # But here we just want to update lang.
    # The existing code queries model directly.
    # For now, to keep it simple and avoid fetching full user entity overhead if not needed:
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        user.lang = lang
        session.commit()
        global_data.user_lang_dic[user_id] = lang
    else:
        raise ValueError(f"No user found with user_id {user_id}")


def check_user_lang(session: Session, user_id: int):
    user = session.query(MyMtlWalletBotUsers.lang).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        return user.lang
    else:
        return None


def my_gettext(user_id: Union[types.CallbackQuery, types.Message, int, str], text: str, param: tuple = (), app_context: AppContext = None) -> str:
    if isinstance(user_id, str):
        lang = user_id
    else:
        user_id = get_user_id(user_id)

        if app_context and app_context.localization_service:
            lang = app_context.localization_service.get_user_lang(user_id)
        elif user_id in global_data.user_lang_dic:
            lang = global_data.user_lang_dic[user_id]
        else:
            with global_data.db_pool.get_session() as session:

                try:
                    user = session.query(MyMtlWalletBotUsers.lang).filter(MyMtlWalletBotUsers.user_id == user_id).first()
                    lang = user.lang if user else 'en'
                except Exception:
                    lang = 'en'
            global_data.user_lang_dic[user_id] = lang

    if app_context and app_context.localization_service:
        text_str = app_context.localization_service.get_text(lang, text)
    else:
        text_str = global_data.lang_dict[lang].get(text, global_data.lang_dict['en'].get(text, f'{text} 0_0'))
    
    text = text_str
    # won't use format if will be error in lang file
    for par in param:
        text = text.replace('{}', str(par), 1)
    return text


def check_user_id(session: Session, user_id: int):
    user_count = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).count()
    return user_count > 0
