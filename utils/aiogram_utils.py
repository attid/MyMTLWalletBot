import sys
from typing import Union

import tzlocal
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio.client import Redis

from loguru import logger
from aiogram import Bot, Dispatcher
from config_reader import config
from aiogram import types
from keyboards.common_keyboards import get_kb_return, get_kb_send
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from utils.lang_utils import get_last_message_id, set_last_message_id, my_gettext
from utils.stellar_utils import stellar_get_balances

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

admin_id = 84131737


class StateSign(StatesGroup):
    sending_xdr = State()


async def send_message(user_id: Union[types.CallbackQuery, types.Message, int], msg: str, reply_markup=None,
                       need_new_msg=None, parse_mode='HTML'):
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    msg_id = get_last_message_id(user_id)
    if need_new_msg:
        new_msg = await bot.send_message(user_id, msg, reply_markup=reply_markup, parse_mode=parse_mode,
                                         disable_web_page_preview=True)
        if msg_id > 0:
            try:
                await bot.delete_message(user_id, msg_id)
            except Exception as ex:
                logger.info(['await send_message, del', user_id, ex])
        set_last_message_id(user_id, new_msg.message_id)
    else:
        try:
            await bot.edit_message_text(msg, user_id, msg_id, reply_markup=reply_markup, parse_mode=parse_mode,
                                        disable_web_page_preview=True)
        except Exception as ex:
            new_msg = await bot.send_message(user_id, msg, reply_markup=reply_markup, parse_mode=parse_mode,
                                             disable_web_page_preview=True)
            set_last_message_id(user_id, new_msg.message_id)


async def cmd_show_sign(chat_id: int, state: FSMContext, msg='', use_send=False):
    # msg = msg + my_gettext(chat_id, 'send_xdr')
    data = await state.get_data()
    tools = data.get('tools')

    if use_send:
        kb = get_kb_send(chat_id)
        if tools:
            kb = get_kb_send(chat_id, with_tools=tools)
    else:
        kb = get_kb_return(chat_id)

    if len(msg) > 4000:
        await send_message(chat_id, my_gettext(chat_id, 'big_xdr'), reply_markup=kb,
                           parse_mode='MARKDOWN')
    else:
        await send_message(chat_id, msg, reply_markup=kb, parse_mode='MARKDOWN')
