import asyncio
import aiohttp
import sys
import tzlocal
from contextlib import suppress
from datetime import datetime
from typing import Union
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio.client import Redis
from aiogram import Bot, Dispatcher
from sqlalchemy.orm import Session
from aiogram import types
from config_reader import config
from keyboards.common_keyboards import get_kb_return, get_kb_send, get_return_button
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from utils.common_utils import get_user_id
from utils.lang_utils import my_gettext

if 'test' in sys.argv:
    bot = Bot(token=config.test_bot_token.get_secret_value(), parse_mode='HTML')
    # storage = MemoryStorage()
    storage = RedisStorage(redis=Redis(host='localhost', port=6379, db=5))
    dp = Dispatcher(storage=storage)
    print('start test')
else:
    bot = Bot(token=config.bot_token.get_secret_value(), parse_mode='HTML')
    # storage = MemoryStorage()
    storage = RedisStorage(redis=Redis(host='localhost', port=6379, db=5))
    dp = Dispatcher(storage=storage)

scheduler = AsyncIOScheduler(timezone=str(tzlocal.get_localzone()))
cheque_queue = asyncio.Queue()
log_queue = asyncio.Queue()

admin_id = 84131737
helper_chat_id = -1001466779498


class StateSign(StatesGroup):
    sending_xdr = State()


class LogQuery:
    def __init__(self, user_id: int, log_operation: str, log_operation_info: str):
        self.user_id = user_id
        self.log_operation = log_operation
        self.log_operation_info = log_operation_info
        self.log_dt = datetime.now()


async def send_message(session: Session, user_id: Union[types.CallbackQuery, types.Message, int], msg: str,
                       reply_markup=None, need_new_msg=None, parse_mode='HTML'):
    user_id = get_user_id(user_id)

    fsm_storage_key = StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id)
    data = await dp.storage.get_data(key=fsm_storage_key)
    msg_id = data.get('last_message_id', 0)
    if need_new_msg:
        new_msg = await bot.send_message(user_id, msg, reply_markup=reply_markup, parse_mode=parse_mode,
                                         disable_web_page_preview=True)
        if msg_id > 0:
            with suppress(TelegramBadRequest):
                await bot.delete_message(user_id, msg_id)
        await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': new_msg.message_id})
    else:
        if msg_id > 0:
            try:
                await bot.edit_message_text(msg, user_id, msg_id, reply_markup=reply_markup, parse_mode=parse_mode,
                                            disable_web_page_preview=True)
                return
            except:
                pass
        new_msg = await bot.send_message(user_id, msg, reply_markup=reply_markup, parse_mode=parse_mode,
                                         disable_web_page_preview=True)
        await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': new_msg.message_id})


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
        chat = await bot.get_chat(user_id)
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
    fsm_storage_key = StorageKey(bot_id=bot.id, user_id=chat_id, chat_id=chat_id)
    # data = await dp.storage.get_data(key=fsm_storage_key)
    await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': msg_id})


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
            if response.headers.get('Content-Type') == 'application/json' or return_type == 'json':
                return response.status, await response.json()
            else:
                return response.status, await response.text()
