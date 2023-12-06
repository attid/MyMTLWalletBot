from typing import Union

import jsonpickle
from aiogram import types
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from loguru import logger
from sqlalchemy.orm import Session

from db.requests import db_get_default_address
from keyboards.common_keyboards import get_kb_resend, get_kb_return, get_return_button
from utils.aiogram_utils import send_message, bot, clear_state, dp
from utils.common_utils import get_user_id
from utils.lang_utils import my_gettext
from utils.stellar_utils import stellar_get_user_account, stellar_get_balance_str, stellar_is_free_wallet, \
    db_is_new_user, \
    db_get_wallets_list


class WalletSettingCallbackData(CallbackData, prefix="WalletSettingCallbackData"):
    action: str
    idx: int


async def get_kb_default(session: Session, chat_id: int, state: FSMContext) -> types.InlineKeyboardMarkup:
    data = await state.get_data()
    buttons = [
        [
            types.InlineKeyboardButton(text='⤵️ ' + my_gettext(chat_id, 'kb_receive'), callback_data="Receive"),
            types.InlineKeyboardButton(text='🔃 ' + my_gettext(chat_id, 'kb_refresh'), callback_data="Refresh"),
            types.InlineKeyboardButton(text='⤴️ ' + my_gettext(chat_id, 'kb_send'), callback_data="Send")
        ],
        [
            types.InlineKeyboardButton(text='🔄 ' + my_gettext(chat_id, 'kb_swap'), callback_data="Swap"),
            types.InlineKeyboardButton(text='💸 ' + my_gettext(chat_id, 'kb_inout'), callback_data="InOut"),
            types.InlineKeyboardButton(text='📊 ' + my_gettext(chat_id, 'kb_market'), callback_data="Market")
        ],
        # [
        #     types.InlineKeyboardButton(text='🥳 ' + "Radio World", callback_data="Fest")
        # ]
    ]

    if data.get('show_more', False):
        if data.get('mtlap', False):
            buttons.append(
                [
                    types.InlineKeyboardButton(text='🖇 ' + my_gettext(chat_id, 'kb_mtlap_tools'),
                                               callback_data="MTLAPTools")
                ]
            )

        buttons.append(
            [
                types.InlineKeyboardButton(text='🏛 ' + my_gettext(chat_id, 'kb_mtl_tools'), callback_data="MTLTools"),
                types.InlineKeyboardButton(text='⚙️ ' + my_gettext(chat_id, 'kb_setting'),
                                           callback_data="WalletSetting")
            ]
        )
        buttons.append([types.InlineKeyboardButton(text='↔️ ' + my_gettext(chat_id, 'kb_change_wallet'),
                                                   callback_data="ChangeWallet")])
        buttons.append([types.InlineKeyboardButton(text='ℹ️ ' + my_gettext(chat_id, 'kb_support'),
                                                   callback_data="Support")])
        if not await stellar_is_free_wallet(session, chat_id):
            buttons.append(
                [types.InlineKeyboardButton(text='🖌 ' + my_gettext(chat_id, 'kb_sign'), callback_data="Sign")])
        buttons.append([types.InlineKeyboardButton(text='≢ ' + my_gettext(chat_id, 'kb_show_less'),
                                                   callback_data="ShowMoreToggle")])
    else:
        buttons.append([types.InlineKeyboardButton(text='≡ ' + my_gettext(chat_id, 'kb_show_more'),
                                                   callback_data="ShowMoreToggle")])
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


async def cmd_show_balance(session: Session, user_id: int, state: FSMContext, need_new_msg=None,
                           refresh_callback: types.CallbackQuery = None):
    # new user ?
    if db_is_new_user(session, user_id):
        await state.update_data(fsm_after_send=jsonpickle.dumps(cmd_show_balance))
        await cmd_change_wallet(user_id, state, session)
    else:
        try:
            # start_time = datetime.now()
            # print(datetime.now(), f'time {datetime.now() - start_time}', 4)
            data = await state.get_data()
            await state.set_state(state=None)
            await clear_state(state)
            user_account = (await stellar_get_user_account(session, user_id)).account.account_id
            simple_account = user_account[:4] + '..' + user_account[-4:]

            link = 'https://stellar.expert/explorer/public/account/' + user_account
            # a = await stellar_get_balance_str(user_id)
            msg = f'<a href="{link}">{simple_account}</a> {my_gettext(user_id, "your_balance")}\n\n' \
                  f'{await stellar_get_balance_str(session, user_id, state=state)}'

            # if str(start_cmd).find('veche_') == 0:
            #    pass
            #    # await cmd_login_to_veche(chat_id, state, start_cmd)
            # else:

            if refresh_callback and msg == data.get('start_msg'):
                await refresh_callback.answer('Nothing to update, the data is up to date.', show_alert=True)
                await state.update_data(start_msg=msg)
            else:
                keyboard = await get_kb_default(session, user_id, state)
                await send_message(session, user_id, msg, reply_markup=keyboard,
                                   need_new_msg=need_new_msg,
                                   parse_mode='HTML')
                await state.update_data(start_msg=msg)

        except Exception as ex:
            logger.info(['cmd_show_balance ', user_id, ex])
            kb = [[types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_change_wallet'),
                                              callback_data="ChangeWallet")]]
            await send_message(session, user_id, my_gettext(user_id, 'load_error'),
                               reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
            await state.update_data(last_message_id=0)


async def cmd_info_message(session: Session, user_id: Union[types.CallbackQuery, types.Message, int],
                           msg: str, send_file=None, resend_transaction=None):
    user_id = get_user_id(user_id)

    if send_file:
        photo = types.FSInputFile(send_file)
        await bot.send_photo(user_id, photo=photo, caption=msg, reply_markup=get_kb_return(user_id))
        fsm_storage_key = StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id)
        data = await dp.storage.get_data(key=fsm_storage_key)
        try:
            await bot.delete_message(user_id, data.get('last_message_id', 0))
        except:
            pass
        await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})
    elif resend_transaction:
        await send_message(session, user_id, msg, reply_markup=get_kb_resend(user_id))
    else:
        await send_message(session, user_id, msg, reply_markup=get_kb_return(user_id))


# user_id = 123456
#    fsm_storage_key = StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id)#
#
#   # Clear user state
#  await dp.storage.set_state(fsm_storage_key, None) #workflow_data

async def cmd_change_wallet(user_id: int, state: FSMContext, session: Session):
    msg = my_gettext(user_id, 'setting_msg')
    default_address = db_get_default_address(session, user_id)
    buttons = []
    wallets = db_get_wallets_list(session, user_id)
    for wallet in wallets:
        active_name = '📌 Active' if wallet.default_wallet == 1 else 'Set active'
        if wallet.free_wallet == 1:
            info_text = '(free)'
        elif wallet.use_pin == 1:
            info_text = '(pin)'
        elif wallet.use_pin == 2:
            info_text = '(pass)'
        elif wallet.use_pin == 10:
            info_text = '(r/o)'
        else:
            info_text = '(0_0)'
        if default_address == wallet.public_key:
            info_text += '📩'
        buttons.append([types.InlineKeyboardButton(text=f"{wallet.public_key[:4]}..{wallet.public_key[-4:]} {info_text}",
                                                   callback_data=WalletSettingCallbackData(action='NAME',
                                                                                           idx=wallet.id).pack()),
                        types.InlineKeyboardButton(text=f"{active_name}",
                                                   callback_data=WalletSettingCallbackData(action='SET_ACTIVE',
                                                                                           idx=wallet.id).pack()),
                        types.InlineKeyboardButton(text=f"Delete",
                                                   callback_data=WalletSettingCallbackData(action='DELETE',
                                                                                           idx=wallet.id).pack())
                        ])
    buttons.append([types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_add_new'), callback_data="AddNew")])
    buttons.append(get_return_button(user_id))

    await send_message(session, user_id, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.update_data(wallets={wallet.id: wallet.public_key for wallet in wallets})
