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


from keyboards.common_keyboards import get_kb_resend, get_kb_return, get_return_button, get_hide_notification_keyboard
from infrastructure.utils.telegram_utils import send_message, clear_state, clear_last_message_id
from infrastructure.utils.common_utils import get_user_id

from other.lang_tools import my_gettext
from infrastructure.utils.common_utils import float2str
from infrastructure.services.app_context import AppContext
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from services.ton_service import TonService


class WalletSettingCallbackData(CallbackData, prefix="WalletSettingCallbackData"):
    action: str
    idx: int


async def get_kb_default(session: Session, chat_id: int, state: FSMContext, app_context: AppContext = None) -> types.InlineKeyboardMarkup:
    data = await state.get_data()

    if data.get('use_ton', False):
        buttons = [
            [types.InlineKeyboardButton(text='⤴️ Send TON', callback_data="SendTon")],
            [types.InlineKeyboardButton(text='⤴️ Send USDt', callback_data="SendTonUSDt")],
            [types.InlineKeyboardButton(text='↔️ ' + my_gettext(chat_id, 'kb_change_wallet', app_context=app_context),
                                        callback_data="ChangeWallet")],
            [types.InlineKeyboardButton(text='ℹ️ ' + my_gettext(chat_id, 'kb_support', app_context=app_context),
                                        callback_data="Support")]]
        return types.InlineKeyboardMarkup(inline_keyboard=buttons)

    buttons = [
        [
            types.InlineKeyboardButton(text='⤵️ ' + my_gettext(chat_id, 'kb_receive', app_context=app_context), callback_data="Receive"),
            types.InlineKeyboardButton(text='🔃 ' + my_gettext(chat_id, 'kb_refresh', app_context=app_context), callback_data="Refresh"),
            types.InlineKeyboardButton(text='⤴️ ' + my_gettext(chat_id, 'kb_send', app_context=app_context), callback_data="Send")
        ],
        [
            types.InlineKeyboardButton(text='🔄 ' + my_gettext(chat_id, 'kb_swap', app_context=app_context), callback_data="Swap"),
            types.InlineKeyboardButton(text='💸 ' + my_gettext(chat_id, 'kb_inout', app_context=app_context), callback_data="InOut"),
            types.InlineKeyboardButton(text='📊 ' + my_gettext(chat_id, 'kb_market', app_context=app_context), callback_data="Market")
        ],
        # [
        #     types.InlineKeyboardButton(text='🥳 ' + "MTLFEST 2024", callback_data="Fest2024")
        # ]
        # app_context passed to keys if needed? 'MTLFEST 2024' is constant.
    ]

    if data.get('show_more', False):
        if data.get('mtlap', False):
            buttons.append(
                [
                    types.InlineKeyboardButton(text='🖇 ' + my_gettext(chat_id, 'kb_mtlap_tools', app_context=app_context),
                                               callback_data="MTLAPTools")
                ]
            )

        buttons.append(
            [
                types.InlineKeyboardButton(text='🏛 ' + my_gettext(chat_id, 'kb_mtl_tools', app_context=app_context), callback_data="MTLTools"),
                types.InlineKeyboardButton(text='⚙️ ' + my_gettext(chat_id, 'kb_setting', app_context=app_context),
                                           callback_data="WalletSetting")
            ]
        )
        buttons.append([types.InlineKeyboardButton(text='↔️ ' + my_gettext(chat_id, 'kb_change_wallet', app_context=app_context),
                                                   callback_data="ChangeWallet")])
        buttons.append([types.InlineKeyboardButton(text='ℹ️ ' + my_gettext(chat_id, 'kb_support', app_context=app_context),
                                                   callback_data="Support")])
        wallet_repo = SqlAlchemyWalletRepository(session)
        default_wallet = await wallet_repo.get_default_wallet(chat_id)
        is_free = default_wallet.is_free if default_wallet else False 
        if not is_free:
            buttons.append(
                [types.InlineKeyboardButton(text='🖌 ' + my_gettext(chat_id, 'kb_sign', app_context=app_context), callback_data="Sign")])
        buttons.append([types.InlineKeyboardButton(text='≢ ' + my_gettext(chat_id, 'kb_show_less', app_context=app_context),
                                                   callback_data="ShowMoreToggle")])
    else:
        buttons.append([types.InlineKeyboardButton(text='≡ ' + my_gettext(chat_id, 'kb_show_more', app_context=app_context),
                                                   callback_data="ShowMoreToggle")])
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)


async def cmd_show_balance(session: Session, user_id: int, state: FSMContext, need_new_msg=None,
                           refresh_callback: types.CallbackQuery = None, app_context: AppContext = None, **kwargs):
    user_repo = SqlAlchemyUserRepository(session)
    user = await user_repo.get_by_id(user_id)
    # new user ?
    if not user:
        await state.update_data(fsm_after_send=jsonpickle.dumps(cmd_show_balance))
        await cmd_change_wallet(user_id, state, session)
    else:
        try:
            # start_time = datetime.now()
            # print(datetime.now(), f'time {datetime.now() - start_time}', 4)
            data = await state.get_data()
            await state.set_state(state=None)
            await clear_state(state)
            msg = await get_start_text(session, state, user_id, app_context=app_context)

            if refresh_callback and msg == data.get('start_msg'):
                await refresh_callback.answer('Nothing to update, the data is up to date.', show_alert=True)
                await state.update_data(start_msg=msg)
            else:
                keyboard = await get_kb_default(session, user_id, state, app_context=app_context)
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


async def get_start_text(session, state, user_id, app_context: AppContext = None):
    from infrastructure.services.wallet_secret_service import SqlAlchemyWalletSecretService
    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    
    secret_service = SqlAlchemyWalletSecretService(session)
    repo = SqlAlchemyWalletRepository(session)
    
    wallet = await repo.get_default_wallet(user_id)
    if await secret_service.is_ton_wallet(user_id):
        mnemonic = await secret_service.get_ton_mnemonic(user_id)
        ton_service = TonService()
        ton_service.from_mnemonic(mnemonic)
        await state.update_data(use_ton=True)
        ton_balance = await ton_service.get_ton_balance()
        usdt_balance = await ton_service.get_usdt_balance()
        warning_message = "⚠️ The TON wallet is in a testing phase. It is not recommended to store amounts that you are not willing to lose."
        return f"""Address: 
<code>{ton_service.wallet.address.to_str(is_bounceable=False)}</code>
TON: {float2str(ton_balance, True)}
USDT: {float2str(usdt_balance, True)}

{warning_message}"""

    # user_account = (await stellar_get_user_account(session, user_id)).account.account_id
    user_account = wallet.public_key
    await state.update_data(use_ton=None)

    simple_account = user_account[:4] + '..' + user_account[-4:]
    
    # Refactored Balance Retrieval via Clean Architecture
    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    from infrastructure.services.stellar_service import StellarService
    from core.use_cases.wallet.get_balance import GetWalletBalance
    from other.config_reader import config
    
    wallet_repo = SqlAlchemyWalletRepository(session)
    info = await wallet_repo.get_info(user_id, user_account)
    link = 'https://viewer.eurmtl.me/account/' + user_account
    from other.asset_visibility_tools import get_asset_visibility, ASSET_VISIBLE
    
    repo = SqlAlchemyWalletRepository(session)
    # Using real horizon from config
    service = StellarService(horizon_url=config.horizon_url)
    use_case = GetWalletBalance(repo, service)
    
    balances = await use_case.execute(user_id)
    
    # Formatting Logic (Presenter layer in Router)
    vis_str = getattr(wallet, "assets_visibility", None)
    
    # Filter visible
    balances = [b for b in balances if get_asset_visibility(vis_str, b.asset_code) == ASSET_VISIBLE]
    
    balance_str = ''
    for balance in balances:
        b_val = float(balance.balance)
        s_liab = float(balance.selling_liabilities)
        
        if s_liab > 0:
            lock = float2str(s_liab, short=True)
            full = float2str(b_val, short=True)
            free = float2str(b_val - s_liab, short=True)
            balance_str += f"{balance.asset_code} : {free} (+{lock}={full})\n"
        else:
            balance_str += f"{balance.asset_code} : {float2str(b_val, short=True)}\n"
            
    if wallet.free_wallet == 1:
        balance_str += 'XLM : <a href="https://telegra.ph/XLM-05-28">?</a>\n'

    # msg = f'<a href="{link}">{simple_account}</a> {info} {my_gettext(user_id, "your_balance")}\n\n' \
    #       f'{await stellar_get_balance_str(session, user_id, state=state)}'
    
    msg = f'<a href="{link}">{simple_account}</a> {info} {my_gettext(user_id, "your_balance", app_context=app_context)}\n\n' \
          f'{balance_str}'
    return msg


async def cmd_info_message(session: Session | None, user_id: Union[types.CallbackQuery, types.Message, int],
                           msg: str, send_file=None, resend_transaction=None, operation_id: str = None,
                           public_key: str = None, wallet_id: int = None, app_context: AppContext = None):
    user_id = get_user_id(user_id)
    
    bot = app_context.bot
    dispatcher = app_context.dispatcher

    if send_file:
        photo = types.FSInputFile(send_file)
        add_buttons = [types.InlineKeyboardButton(text=my_gettext(user_id, 'manage_assets_msg'),
                                                  callback_data="ManageAssetsMenu")]
        await bot.send_photo(user_id, photo=photo, caption=msg,
                                         reply_markup=get_kb_return(user_id, add_buttons))
        fsm_storage_key = StorageKey(bot_id=bot.id, user_id=user_id, chat_id=user_id)
        data = await dispatcher.storage.get_data(key=fsm_storage_key)
        with suppress(TelegramBadRequest):
            await bot.delete_message(user_id, data.get('last_message_id', 0))
        await clear_last_message_id(user_id, app_context=app_context)

    elif resend_transaction:
        await send_message(None, user_id, msg, reply_markup=get_kb_resend(user_id))
    elif operation_id:
        keyboard = get_hide_notification_keyboard(user_id, operation_id, wallet_id)
        await send_message(None, user_id, msg, reply_markup=keyboard)
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
    repo = SqlAlchemyWalletRepository(session)
    wallets = await repo.get_all_active(user_id)
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
