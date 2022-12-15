from typing import Union

from aiogram import types

from utils.lang_utils import my_gettext


def get_return_button(user_id: Union[types.CallbackQuery, types.Message, int], text=None, callback=None) -> list:
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    if text is None:
        text = my_gettext(user_id, 'kb_back')

    if callback is None:
        callback = "Return"

    return [types.InlineKeyboardButton(text=text, callback_data=callback)]


def get_kb_return(user_id: Union[types.CallbackQuery, types.Message, int]) -> types.InlineKeyboardMarkup:
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    buttons = [get_return_button(user_id)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def get_kb_del_return(user_id: Union[types.CallbackQuery, types.Message, int]) -> types.InlineKeyboardMarkup:
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    buttons = [get_return_button(user_id,text='Delete and Return', callback='DeleteReturn')]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def get_kb_yesno_send_xdr(user_id: Union[types.CallbackQuery, types.Message, int],
                          add_button_memo: bool = False) -> types.InlineKeyboardMarkup:
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_yes'),
                                    callback_data="Yes_send_xdr"),
         types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_no'),
                                    callback_data="Return"),
         ]
    ]

    if add_button_memo:
        buttons.append([types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_memo'), callback_data="Memo")])

    buttons.append(get_return_button(user_id))

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def get_kb_send(user_id: int, with_tools: bool = False) -> types.InlineKeyboardMarkup:
    buttons = [[types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_send'), callback_data="SendTr")]]

    if with_tools:
        buttons.append([types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_send_tools'),
                                                   callback_data="SendTools")])
    buttons.append(get_return_button(user_id))
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def get_kb_resend(user_id: int) -> types.InlineKeyboardMarkup:
    buttons = [[types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_resend'), callback_data="ReSend")],
               get_return_button(user_id)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

