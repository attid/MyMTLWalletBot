import logging
import sys
from typing import Union
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from app_logger import logger
from aiogram import Bot, Dispatcher
from config_reader import config
from aiogram import types
from keyboards.common_keyboards import get_kb_return, get_kb_send, get_kb_resend
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from utils.lang_utils import get_last_message_id, set_last_message_id, my_gettext
from utils.stellar_utils import stellar_get_balance_str, stellar_get_user_account, stellar_is_free_wallet

if 'test' in sys.argv:
    bot = Bot(token=config.test_bot_token.get_secret_value(), parse_mode='HTML')
    # storage = RedisStorage2('localhost', 6379, db=5, pool_size=10, prefix='my_fsm_key')
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    print('start test')
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
else:
    bot = Bot(token=config.bot_token.get_secret_value(), parse_mode='HTML')
    # storage = RedisStorage2('localhost', 6379, db=5, pool_size=10, prefix='my_fsm_key')
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)


scheduler = AsyncIOScheduler()

class StateSign(StatesGroup):
    sending_xdr = State()


async def send_message(user_id: Union[types.CallbackQuery, types.Message, int], msg: str, reply_markup=None,
                       need_new_msg=None, parse_mode=None):
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


async def cmd_info_message(user_id: Union[types.CallbackQuery, types.Message, int], msg: str, state: FSMContext,
                           send_file=None, resend_transaction=None):
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    if send_file:
        print(send_file)
        photo = types.FSInputFile(send_file)
        # await bot.send_photo(chat_id=message.chat.id, photo=photo)
        # file = InputMedia(media=types.InputFile(send_file))
        await bot.send_photo(user_id, photo=photo, caption=msg, parse_mode='MARKDOWN')
        try:
            await bot.delete_message(user_id, get_last_message_id(user_id))
        except:
            pass
        await cmd_show_balance(user_id, state, need_new_msg=True)
    elif resend_transaction:
        await send_message(user_id, msg, reply_markup=get_kb_resend(user_id), parse_mode='MARKDOWN')
    else:
        await send_message(user_id, msg, reply_markup=get_kb_return(user_id), parse_mode='MARKDOWN')


async def cmd_show_sign(chat_id: int, state: FSMContext, msg='', use_send=False):
    msg = msg + my_gettext(chat_id, 'send_xdr')
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


async def cmd_show_balance(chat_id: int, state: FSMContext, need_new_msg=None):
    try:
        data = await state.get_data()
        start_cmd = data.get('start_cmd')
        await state.clear()

        link = 'https://stellar.expert/explorer/public/account/' + stellar_get_user_account(chat_id).account.account_id
        msg = my_gettext(chat_id, 'your_balance') + \
              f'(<a href="{link}">expert link</a>)\n{stellar_get_balance_str(chat_id)}'

        if str(start_cmd).find('veche_') == 0:
            pass
            # await cmd_login_to_veche(chat_id, state, start_cmd)
        else:
            await send_message(chat_id, msg, reply_markup=get_kb_default(chat_id), need_new_msg=need_new_msg,
                               parse_mode='HTML')
    except Exception as ex:
        logger.info(['cmd_show_balance ', chat_id, ex])
        kb = [[types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_change_wallet'), callback_data="Setting")]]
        await send_message(chat_id, my_gettext(chat_id, 'load_error'),
                           reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
        # set_last_message_id(chat_id, 0)


def get_kb_default(chat_id: int) -> types.InlineKeyboardMarkup:
    buttons = [
        [
            types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_receive'), callback_data="Receive"),
            types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_send'), callback_data="Send")
        ],
        [
            types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_swap'), callback_data="Swap"),
            types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_market'), callback_data="Market")
        ],
        [types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_mtl_tools'), callback_data="MTLTools")],
        [types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_setting'), callback_data="WalletSetting")],
        [types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_change_wallet'), callback_data="Setting")],
        [types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_support'), callback_data="Support")]
    ]
    if not stellar_is_free_wallet(chat_id):
        buttons.append([types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_sign'), callback_data="Sign")])

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard
