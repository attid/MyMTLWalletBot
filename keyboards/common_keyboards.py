from typing import Union
from aiogram import types

from utils.common_utils import get_user_id
from utils.lang_utils import my_gettext


def get_return_button(user_id_or_lang: Union[types.CallbackQuery, types.Message, int, str], text=None, callback=None) -> list:
    if text is None:
        text = my_gettext(user_id_or_lang, 'kb_back')

    if callback is None:
        callback = "Return"

    return [types.InlineKeyboardButton(text=text, callback_data=callback)]


def get_kb_return(user_id: Union[types.CallbackQuery, types.Message, int]) -> types.InlineKeyboardMarkup:
    user_id = get_user_id(user_id)

    buttons = [get_return_button(user_id)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def get_kb_del_return(user_id: Union[types.CallbackQuery, types.Message, int]) -> types.InlineKeyboardMarkup:
    user_id = get_user_id(user_id)

    buttons = [get_return_button(user_id, text='Delete and Return', callback='DeleteReturn')]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def get_kb_yesno_send_xdr(user_id: Union[types.CallbackQuery, types.Message, int],
                          add_button_memo: bool = False) -> types.InlineKeyboardMarkup:
    user_id = get_user_id(user_id)

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
    buttons = [[types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_send_tr'), callback_data="SendTr")]]

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


def get_kb_offers_cancel(user_id: int, data: dict) -> types.InlineKeyboardMarkup:
    """
        Create keyboard with optional checkbox-button '🟢 Cancel offers' and 'Return'-button
    """
    buttons = []
    if data.get('send_asset_blocked_sum', 0.0) > 0:
        cancel_offers_state = '🟢' if data.get('cancel_offers', False) else '⚪️'
        btn_txt = my_gettext(
            user_id,
            'kb_cancel_offers',
            (cancel_offers_state, data.get('send_asset_code'))
        )
        btn = [types.InlineKeyboardButton(text=btn_txt, callback_data='CancelOffers')]
        buttons.append(btn)

    buttons.append(get_return_button(user_id))

    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def get_kb_limits(user_id: int, off_limit: int) -> types.InlineKeyboardMarkup:
    buttons = []
    state = '🟢' if off_limit == 1 else '⚪️'
    btn_txt = my_gettext(
        user_id,
        'kb_update_limit',
        (state,)
    )
    btn = [types.InlineKeyboardButton(text=btn_txt, callback_data='OffLimits')]
    buttons.append(btn)

    buttons.append(get_return_button(user_id))

    return types.InlineKeyboardMarkup(inline_keyboard=buttons)
