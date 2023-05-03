import json
from os import listdir
from typing import Union
import fb
from aiogram import types

from utils.common_utils import get_user_id

user_lang_dic = {}
lang_dict = {}

for file in listdir("langs/"):
    if file.endswith(".json"):
        with open("langs/" + file, "r") as fp:
            lang_dict[file.split('.')[0]] = json.load(fp)


def get_user_lang(user_id: int):
    try:
        lang = fb.execsql1(f"select first 1 m.lang from mymtlwalletbot_users m where m.user_id = ?", (user_id,), 'en')
        if lang is None:
            lang = 'en'
        return lang
    except Exception as ex:
        return 'en'


def change_user_lang(user_id: int, lang: str):
    fb.execsql("update mymtlwalletbot_users m set m.lang = ? where m.user_id = ?", (lang, user_id,))
    user_lang_dic[user_id] = lang


def check_user_lang(user_id: int):
    return fb.execsql1("select m.lang from mymtlwalletbot_users m where m.user_id = ?", (user_id,), None)


def my_gettext(user_id: Union[types.CallbackQuery, types.Message, int], text: str, param: tuple = ()) -> str:
    user_id = get_user_id(user_id)

    if user_id in user_lang_dic:
        lang = user_lang_dic[user_id]
    else:
        lang = get_user_lang(user_id)
        user_lang_dic[user_id] = lang
    text: str = lang_dict[lang].get(text, lang_dict['en'].get(text, f'{text} 0_0'))
    # won't use format if will be error in lang file
    for par in param:
        text = text.replace('{}', str(par), 1)
    return text


def set_last_message_id(user_id: int, message_id: int):
    if get_last_message_id(user_id) != message_id:
        fb.execsql(f"update mymtlwalletbot_users set message_id = ? where user_id = ?", (message_id, user_id))


def check_user_id(user_id: int):
    return fb.execsql1(f"select count(*)  from mymtlwalletbot_users where user_id = ?", (user_id,), 0) > 0


def get_last_message_id(user_id: int):
    try:
        return fb.execsql1(f"select first 1 u.message_id from mymtlwalletbot_users u where u.user_id = ?", (user_id,),
                           0)
    except Exception as ex:
        return 0
