from typing import Union
from aiogram import types
from loguru import logger

from other.common_tools import get_user_id
from other.lang_tools import my_gettext


def get_return_button(user_id_or_lang: Union[types.CallbackQuery, types.Message, int, str], text=None,
                      callback=None) -> list:
    if text is None:
        text = my_gettext(user_id_or_lang, 'kb_back')

    if callback is None:
        callback = "Return"

    return [types.InlineKeyboardButton(text=text, callback_data=callback)]


def get_kb_return(user_id: Union[types.CallbackQuery, types.Message, int],
                  add_buttons=None) -> types.InlineKeyboardMarkup:
    user_id = get_user_id(user_id)

    if add_buttons:
        buttons = [add_buttons, get_return_button(user_id)]
    else:
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


def get_kb_send(user_id: int, with_tools: bool = False, tool_name: str = 'eurmtl.me', can_send=True) -> types.InlineKeyboardMarkup:
    buttons = []

    # Если есть колбек (tool_name == 'callback'), не показываем кнопку отправки в блокчейн
    if can_send:
        buttons.append([types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_send_tr'), callback_data="SendTr")])

    # Добавляем кнопку инструментов, если with_tools == True
    if with_tools:
        buttons.append([types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_send_tools', (tool_name,)),
                                                   callback_data="SendTools")])

    # Всегда добавляем кнопку Decode и Return
    buttons.append([types.InlineKeyboardButton(text='Decode',
                                               callback_data="Decode")])
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

def get_kb_swap_confirm(user_id: int, data: dict) -> types.InlineKeyboardMarkup:
    """
    Create keyboard for swap confirmation with:
    - Optional 'Cancel offers' checkbox
    - 'Specify exact amount to receive' button
    - 'Return' button
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

    # Add button for strict receive scenario
    buttons.append([types.InlineKeyboardButton(
        text=my_gettext(user_id, 'kb_strict_receive'),
        callback_data='SwapStrictReceive'
    )])

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


def get_kb_return_url(user_id: int, return_url: str) -> types.InlineKeyboardMarkup:
    """
    Create a keyboard with a return_url button and a return button.
    """
    buttons = []

    # Validate return_url for Telegram compatibility
    if return_url and _is_valid_telegram_url(return_url):
        buttons.append([types.InlineKeyboardButton(
            text=my_gettext(user_id, 'return_to_site'),
            url=return_url
        )])
        logger.info(f'return_url: {return_url}')
    else:
        logger.warning(f'Invalid return_url for Telegram: {return_url}')

    buttons.append(get_return_button(user_id))
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


def _is_valid_telegram_url(url: str) -> bool:
    """
    Check if URL is valid for Telegram inline keyboard buttons.
    Telegram requires HTTPS URLs that are publicly accessible.
    """
    if not url:
        return False

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)

        # Must be HTTPS
        if parsed.scheme != 'https':
            return False

        # Must have a valid hostname (not localhost, 127.0.0.1, etc.)
        hostname = parsed.hostname
        if not hostname or hostname in ('localhost', '127.0.0.1', '0.0.0.0'):
            return False

        # Must have a valid domain (not IP addresses in some cases)
        if hostname.replace('.', '').isdigit():
            return False

        return True
    except Exception:
        return False
