from typing import Union

from aiogram import types
from aiogram.fsm.context import FSMContext

from loguru import logger
from keyboards.common_keyboards import get_kb_resend, get_kb_return
from utils.aiogram_utils import send_message, bot
from utils.lang_utils import my_gettext, set_last_message_id, get_last_message_id
from utils.stellar_utils import stellar_get_user_account, stellar_get_balance_str, stellar_is_free_wallet


def get_kb_default(chat_id: int) -> types.InlineKeyboardMarkup:
    buttons = [
        [
            types.InlineKeyboardButton(text='⤵️ ' + my_gettext(chat_id, 'kb_receive'), callback_data="Receive"),
            types.InlineKeyboardButton(text='⤴️ ' + my_gettext(chat_id, 'kb_send'), callback_data="Send")
        ],
        [
            types.InlineKeyboardButton(text='🔄 ' + my_gettext(chat_id, 'kb_swap'), callback_data="Swap"),
            types.InlineKeyboardButton(text='🚼 ' + my_gettext(chat_id, 'kb_market'), callback_data="Market")
        ],
        [types.InlineKeyboardButton(text='🏛 ' + my_gettext(chat_id, 'kb_mtl_tools'), callback_data="MTLTools")],
        [types.InlineKeyboardButton(text='⚙️ ' + my_gettext(chat_id, 'kb_setting'), callback_data="WalletSetting")],
        [types.InlineKeyboardButton(text='🔄 ' + my_gettext(chat_id, 'kb_change_wallet'), callback_data="ChangeWallet")],
        [types.InlineKeyboardButton(text='ℹ️ ' + my_gettext(chat_id, 'kb_support'), callback_data="Support")]
    ]
    if not stellar_is_free_wallet(chat_id):
        buttons.append([types.InlineKeyboardButton(text='🖌 ' + my_gettext(chat_id, 'kb_sign'), callback_data="Sign")])

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

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
        kb = [[types.InlineKeyboardButton(text=my_gettext(chat_id, 'kb_change_wallet'), callback_data="ChangeWallet")]]
        await send_message(chat_id, my_gettext(chat_id, 'load_error'),
                           reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
        set_last_message_id(chat_id, 0)


async def cmd_info_message(user_id: Union[types.CallbackQuery, types.Message, int], msg: str, state: FSMContext,
                           send_file=None, resend_transaction=None):
    if isinstance(user_id, types.CallbackQuery):
        user_id = user_id.from_user.id
    elif isinstance(user_id, types.Message):
        user_id = user_id.from_user.id
    else:
        user_id = user_id

    if send_file:
        photo = types.FSInputFile(send_file)
        await bot.send_photo(user_id, photo=photo, caption=msg)
        try:
            await bot.delete_message(user_id, get_last_message_id(user_id))
        except:
            pass
        await cmd_show_balance(user_id, state, need_new_msg=True)
    elif resend_transaction:
        await send_message(user_id, msg, reply_markup=get_kb_resend(user_id))
    else:
        await send_message(user_id, msg, reply_markup=get_kb_return(user_id))
