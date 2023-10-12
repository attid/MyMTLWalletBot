import json
from os import listdir
from typing import Union
from aiogram import types
from sqlalchemy.orm import Session, sessionmaker

from db.models import MyMtlWalletBotUsers
from db.requests import get_user_lang
from utils.common_utils import get_user_id

user_lang_dic = {}
lang_dict = {}
lang_session_maker: sessionmaker

for file in listdir("langs/"):
    if file.endswith(".json"):
        with open("langs/" + file, "r") as fp:
            lang_dict[file.split('.')[0]] = json.load(fp)


def change_user_lang(session: Session, user_id: int, lang: str):
    user = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).one_or_none()
    if user is not None:
        user.lang = lang
        session.commit()
        user_lang_dic[user_id] = lang  # assuming user_lang_dic is accessible
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

        if user_id in user_lang_dic:
            lang = user_lang_dic[user_id]
        else:
            with lang_session_maker() as session:
                lang = get_user_lang(session, user_id)
            user_lang_dic[user_id] = lang

    text: str = lang_dict[lang].get(text, lang_dict['en'].get(text, f'{text} 0_0'))
    # won't use format if will be error in lang file
    for par in param:
        text = text.replace('{}', str(par), 1)
    return text

def check_user_id(session: Session, user_id: int):
    user_count = session.query(MyMtlWalletBotUsers).filter(MyMtlWalletBotUsers.user_id == user_id).count()
    return user_count > 0