from contextlib import suppress
from typing import Union

import jsonpickle
from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from loguru import logger
from sqlalchemy.orm import Session

from db.requests import get_wallet_info, db_get_default_wallet
from keyboards.common_keyboards import get_kb_resend, get_kb_return, get_return_button
from other.aiogram_tools import send_message, clear_state, clear_last_message_id
from other.common_tools import get_user_id
from other.global_data import global_data
from other.lang_tools import my_gettext
from other.stellar_tools import stellar_get_user_account, stellar_get_balance_str, stellar_is_free_wallet, \
    db_is_new_user, \
    db_get_wallets_list, float2str
from services.ton_service import TonService


class WalletSettingCallbackData(CallbackData, prefix="WalletSettingCallbackData"):
    action: str
    idx: int


async def get_kb_default(session: Session, chat_id: int, state: FSMContext) -> types.InlineKeyboardMarkup:
    data = await state.get_data()

    if data.get('use_ton', False):
        buttons = [
            [types.InlineKeyboardButton(text='⤴️ Send TON', callback_data="SendTon")],
            [types.InlineKeyboardButton(text='⤴️ Send USDt', callback_data="SendTonUSDt")],
            [types.InlineKeyboardButton(text='↔️ ' + my_gettext(chat_id, 'kb_change_wallet'),
                                        callback_data="ChangeWallet")],
            [types.InlineKeyboardButton(text='ℹ️ ' + my_gettext(chat_id, 'kb_support'),
                                        callback_data="Support")]]
        return types.InlineKeyboardMarkup(inline_keyboard=buttons)

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
        #     types.InlineKeyboardButton(text='🥳 ' + "MTLFEST 2024", callback_data="Fest2024")
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
            msg = await get_start_text(session, state, user_id)

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
            await clear_state(state)
            await state.update_data(last_message_id=0)


async def get_start_text(session, state, user_id):
    wallet = db_get_default_wallet(session=session, user_id=user_id)
    if wallet.secret_key == 'TON':
        ton_service = TonService()
        ton_service.from_mnemonic(wallet.seed_key)
        await state.update_data(use_ton=True)
        ton_balance = await ton_service.get_ton_balance()
        usdt_balance = await ton_service.get_usdt_balance()
        warning_message = "⚠️ The TON wallet is in a testing phase. It is not recommended to store amounts that you are not willing to lose."
        return f"""Address: 
<code>{ton_service.wallet.address.to_str(is_bounceable=False)}</code>
TON: {float2str(ton_balance, True)}
USDT: {float2str(usdt_balance, True)}

{warning_message}"""

    user_account = (await stellar_get_user_account(session, user_id)).account.account_id

    simple_account = user_account[:4] + '..' + user_account[-4:]
    info = get_wallet_info(session, user_id, user_account)
    link = 'https://stellar.expert/explorer/public/account/' + user_account
    # a = await stellar_get_balance_str(user_id)
    msg = f'<a href="{link}">{simple_account}</a> {info} {my_gettext(user_id, "your_balance")}\n\n' \
          f'{await stellar_get_balance_str(session, user_id, state=state)}'
    return msg


async def cmd_info_message(session: Session | None, user_id: Union[types.CallbackQuery, types.Message, int],
                           msg: str, send_file=None, resend_transaction=None):
    user_id = get_user_id(user_id)

    if send_file:
        photo = types.FSInputFile(send_file)
        add_buttons = [types.InlineKeyboardButton(text=my_gettext(user_id, 'manage_assets_msg'),
                                                  callback_data="ManageAssetsMenu")]
        await global_data.bot.send_photo(user_id, photo=photo, caption=msg,
                                         reply_markup=get_kb_return(user_id, add_buttons))
        fsm_storage_key = StorageKey(bot_id=global_data.bot.id, user_id=user_id, chat_id=user_id)
        data = await global_data.dispatcher.storage.get_data(key=fsm_storage_key)
        with suppress(TelegramBadRequest):
            await global_data.bot.delete_message(user_id, data.get('last_message_id', 0))
        await clear_last_message_id(user_id)

    elif resend_transaction:
        await send_message(None, user_id, msg, reply_markup=get_kb_resend(user_id))
    else:
        await send_message(None, user_id, msg, reply_markup=get_kb_return(user_id))


# user_id = 123456
#    fsm_storage_key = StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id)#
#
#   # Clear user state
#  await dp.storage.set_state(fsm_storage_key, None) #workflow_data

async def cmd_change_wallet(user_id: int, state: FSMContext, session: Session):
    msg = my_gettext(user_id, 'setting_msg')
    buttons = []
    wallets = db_get_wallets_list(session, user_id)
    for wallet in wallets:
        active_name = '📌 Active' if wallet.default_wallet == 1 else 'Set active'
        buttons.append(
            [types.InlineKeyboardButton(text=f"{wallet.public_key[:4]}..{wallet.public_key[-4:]}",
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
