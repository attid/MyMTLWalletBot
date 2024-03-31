import json
from os import listdir
from typing import Union
from aiogram import types
from sqlalchemy.orm import Session

from config_reader import start_path
from db.models import MyMtlWalletBotUsers
from db.requests import get_user_lang
from utils.common_utils import get_user_id
from utils.global_data import global_data

for file in listdir(f"{start_path}/langs/"):
    if file.endswith(".json"):
        with open(f"{start_path}/langs/" + file, "r") as fp:
            global_data.lang_dict[file.split('.')[0]] = json.load(fp)


def change_user_lang(session: Session, user_id: int, lang: str):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        user.lang = lang
        session.commit()
        global_data.user_lang_dic[user_id] = lang  # assuming user_lang_dic is accessible
    else:
        raise ValueError(f"No user found with user_id {user_id}")


def check_user_lang(session: Session, user_id: int):
    user = session.query(MyMtlWalletBotUsers.lang).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        return user.lang
    else:
        return None


def my_gettext(user_id: Union[types.CallbackQuery, types.Message, int, str], text: str, param: tuple = ()) -> str:
    if isinstance(user_id, str):
        lang = user_id
    else:
        user_id = get_user_id(user_id)

        if user_id in global_data.user_lang_dic:
            lang = global_data.user_lang_dic[user_id]
        else:
            with global_data.db_pool() as session:
                lang = get_user_lang(session, user_id)
            global_data.user_lang_dic[user_id] = lang

    text: str = global_data.lang_dict[lang].get(text, global_data.lang_dict['en'].get(text, f'{text} 0_0'))
    # won't use format if will be error in lang file
    for par in param:
        text = text.replace('{}', str(par), 1)
    return text


def check_user_id(session: Session, user_id: int):
    user_count = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).count()
    return user_count > 0
