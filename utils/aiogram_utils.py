import aiohttp
from contextlib import suppress
from typing import Union
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from loguru import logger
from sqlalchemy.orm import Session
from aiogram import types
from keyboards.common_keyboards import get_kb_return, get_kb_send, get_return_button
from utils.common_utils import get_user_id
from utils.global_data import global_data
from utils.lang_utils import my_gettext


async def send_message(session: Session, user_id: Union[types.CallbackQuery, types.Message, int], msg: str,
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

    if not use_send:
        await get_web_request('POST', url="https://vault.lobstr.co/api/transactions/",
                              json={"xdr": xdr_uri})

    if use_send:
        kb = get_kb_send(chat_id)
        if tools:
            kb = get_kb_send(chat_id, with_tools=tools)
    elif xdr_uri:
        from urllib.parse import urlencode
        params = {'xdr': xdr_uri}
        url = 'https://eurmtl.me/uri?' + urlencode(params)

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


async def check_username(user_id: int) -> str:
    with suppress(TelegramBadRequest):
        chat = await global_data.bot.get_chat(user_id)
        return chat.username


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
            'free_xlm': data.get('free_xlm', 0)
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


async def get_web_request(method, url, json=None, headers=None, data=None, return_type=None):
    async with aiohttp.ClientSession() as web_session:
        if method.upper() == 'POST':
            request_coroutine = web_session.post(url, json=json, headers=headers, data=data)
        elif method.upper() == 'GET':
            request_coroutine = web_session.get(url, headers=headers, params=data)
        else:
            raise ValueError("Неизвестный метод запроса")

        async with request_coroutine as response:
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type or return_type == 'json':
                return response.status, await response.json()
            else:
                return response.status, await response.text()


async def get_web_decoded_xdr(xdr):
    status, response_json = await get_web_request('POST', url="https://eurmtl.me/remote/decode", json={"xdr": xdr})
    if status == 200:
        msg = response_json['text']
    else:
        msg = "Ошибка запроса"
    return msg
