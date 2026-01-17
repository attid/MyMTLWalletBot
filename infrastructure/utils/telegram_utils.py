from contextlib import suppress
from typing import Union, Any
from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from loguru import logger
from sqlalchemy.orm import Session

from keyboards.common_keyboards import get_kb_return, get_kb_send, get_return_button
from other.global_data import global_data
from other.lang_tools import my_gettext
from other.web_tools import get_web_request

from infrastructure.utils.common_utils import get_user_id

TELEGRAM_API_ERROR: Any = object()


async def send_message(session: Session | None, user_id: Union[types.CallbackQuery, types.Message, int], msg: str,
                       reply_markup=None, need_new_msg=None, parse_mode='HTML'):
    user_id = get_user_id(user_id)

    fsm_storage_key = StorageKey(bot_id=global_data.bot.id, user_id=user_id, chat_id=user_id)
    data = await global_data.dispatcher.storage.get_data(key=fsm_storage_key)
    msg_id = data.get('last_message_id', 0)
    if need_new_msg:
        new_msg = await global_data.bot.send_message(user_id, msg, reply_markup=reply_markup, parse_mode=parse_mode,
                                                     disable_web_page_preview=True)
        if msg_id > 0:
            with suppress(TelegramBadRequest):
                await global_data.bot.delete_message(user_id, msg_id)
        await global_data.dispatcher.storage.update_data(key=fsm_storage_key,
                                                         data={'last_message_id': new_msg.message_id})
    else:
        if msg_id > 0:
            try:
                await global_data.bot.edit_message_text(text=msg, chat_id=user_id, message_id=msg_id,
                                                        reply_markup=reply_markup, parse_mode=parse_mode,
                                                        disable_web_page_preview=True)
                return
            except Exception as ex:
                logger.info(['send_message edit_text error', ex.__class__])

        new_msg = await global_data.bot.send_message(user_id, msg, reply_markup=reply_markup, parse_mode=parse_mode,
                                                     disable_web_page_preview=True)
        await global_data.dispatcher.storage.update_data(key=fsm_storage_key,
                                                         data={'last_message_id': new_msg.message_id})


async def cmd_show_sign(session: Session, chat_id: int, state: FSMContext, msg='', use_send=False, xdr_uri=None,
                        parse_mode='HTML'):
    # msg = msg + my_gettext(chat_id, 'send_xdr')
    data = await state.get_data()
    tools = data.get('tools')
    callback_url = data.get('callback_url')
    wallet_connect = data.get('wallet_connect')

    if not use_send:
        await get_web_request('POST', url="https://vault.lobstr.co/api/transactions/",
                              json={"xdr": xdr_uri})

    if use_send:
        kb = get_kb_send(chat_id)
        if tools:
            kb = get_kb_send(chat_id, with_tools=tools)
        if callback_url:
            kb = get_kb_send(chat_id, with_tools=True, tool_name='callback', can_send=False)
        if wallet_connect:
            kb = get_kb_send(chat_id, with_tools=True, tool_name='wallet_connect', can_send=False)

    elif xdr_uri:
        from urllib.parse import urlencode, quote
        params = {'xdr': xdr_uri}
        url = 'https://eurmtl.me/uri?' + urlencode(params, quote_via=quote)

        buttons = [get_return_button(chat_id),
                   [types.InlineKeyboardButton(text='Sign Tools', url=url)]
                   ]
        kb = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    else:
        kb = get_kb_return(chat_id)

    if len(msg) > 4000:
        await send_message(session, chat_id, my_gettext(chat_id, 'big_xdr'), reply_markup=kb,
                           parse_mode=parse_mode)
    else:
        await send_message(session, chat_id, msg, reply_markup=kb, parse_mode=parse_mode)


async def check_username(user_id: int) -> Union[str, None, object]:
    try:
        chat = await global_data.bot.get_chat(user_id)
        return chat.username
    except TelegramBadRequest as e:
        logger.warning(f"Telegram API error (TelegramBadRequest) when checking username for user_id={user_id}: {e}")
        return TELEGRAM_API_ERROR
    except Exception as e:
        logger.error(f"Unexpected error when checking username for user_id={user_id}: {e}")
        return TELEGRAM_API_ERROR


async def clear_state(state: FSMContext):
    # если надо очистить стейт то удаляем все кроме этого
    data = await state.get_data()
    await state.set_data(
        {
            'show_more': data.get('show_more', False),
            'user_name': data.get('user_name', ''),
            'user_id': data.get('user_id', 1),
            'user_lang': data.get('user_lang', 'en'),
            'last_message_id': data.get('last_message_id', 0),
            'mtlap': data.get('mtlap', None),
            'free_xlm': data.get('free_xlm', 0),
            'use_ton': data.get('use_ton', None),
        }
    )


def long_line() -> str:
    return ''.ljust(53, '⠀')


async def set_last_message_id(chat_id: int, msg_id: int):
    fsm_storage_key = StorageKey(bot_id=global_data.bot.id, user_id=chat_id, chat_id=chat_id)
    # data = await dp.storage.get_data(key=fsm_storage_key)
    await global_data.dispatcher.storage.update_data(key=fsm_storage_key, data={'last_message_id': msg_id})


async def clear_last_message_id(chat_id: int):
    await set_last_message_id(chat_id, 0)
