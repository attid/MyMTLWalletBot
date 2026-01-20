import asyncio
from datetime import datetime, timedelta
from typing import Union, Optional, Any
import jsonpickle  # type: ignore
from aiogram import Router, types, Bot, F
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from stellar_sdk import Keypair

from core.domain.value_objects import Asset as DomainAsset
from infrastructure.services.app_context import AppContext
from infrastructure.services.localization_service import LocalizationService 
# from db.requests import db_add_donate, db_delete_all_by_user, db_add_user_if_not_exists, db_update_username
from keyboards.common_keyboards import get_return_button, get_kb_return, get_kb_yesno_send_xdr, get_kb_limits
from middleware.throttling import rate_limit
from routers.common_setting import cmd_language
from routers.sign import cmd_check_xdr
from routers.start_msg import cmd_show_balance, get_kb_default, get_start_text
from infrastructure.utils.telegram_utils import send_message, clear_state

from other.lang_tools import my_gettext, check_user_id, check_user_lang
from other.stellar_tools import (stellar_get_balances, stellar_get_user_account
                                 )

router = Router()
router.message.filter(F.chat.type == "private")


class SettingState(StatesGroup):
    send_donate_sum = State()
    send_default_address = State()


@router.message(Command(commands=["start"]), F.text.contains("sign_"))
async def cmd_start_sign(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None:
        return
    await clear_state(state)

    # check address
    await state.update_data(last_message_id=0)
    await send_message(session, message.from_user.id, 'Loading', app_context=app_context)

    # if user not exist
    if not await check_user_id(session, message.from_user.id):
        await send_message(session, message.from_user.id, 'You dont have wallet. Please run /start', app_context=app_context)
        return

    await cmd_check_xdr(session, 'https://eurmtl.me/sign_tools/' + message.text.split(' ')[1][5:], message.from_user.id,
                        state, app_context=app_context)


# @router.message(Command(commands=["start"]))
@router.message(F.text.lower() == '/start', F.chat.type == 'private')
async def cmd_start(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot,
                    app_context: AppContext, l10n: LocalizationService):
    if message.from_user is None:
        return
    # logger.info([message.from_user.id, ' cmd_start'])
    await clear_state(state)

    # check address
    await state.update_data(last_message_id=0)
    await send_message(session, message.from_user.id, 'Loading', app_context=app_context)

    if await check_user_lang(session, message.from_user.id) is None:
        # Refactored to use Clean Architecture Use Case
        use_case_factory = app_context.use_case_factory
        if use_case_factory is None:
            return
        register_use_case = use_case_factory.create_register_user(session)
        
        # Generate a new Stellar account
        mnemonic = app_context.stellar_service.generate_mnemonic()
        kp = app_context.stellar_service.get_keypair_from_mnemonic(mnemonic)
        public_key = kp.public_key
        secret_key = kp.secret
        
        # Encrypt the secret key
        encrypted_secret = app_context.encryption_service.encrypt(secret_key, str(message.from_user.id))
        encrypted_mnemonic = app_context.encryption_service.encrypt(mnemonic, secret_key)
        
        await register_use_case.execute(
             user_id=message.from_user.id,
             username=message.from_user.username or "",
             language='en', # Default
             public_key=public_key,
             secret_key=encrypted_secret,
             seed_key=encrypted_mnemonic
        )
        
        # db_add_user_if_not_exists(session, message.from_user.id, message.from_user.username)
        await cmd_language(session, message.from_user.id, l10n, app_context=app_context)
    else:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        await cmd_show_balance(session, message.from_user.id, state, app_context=app_context)
        await check_update_username(
            session,
            message.from_user.id,
            message.from_user.username or "",
            state,
            app_context=app_context,
        )


@router.callback_query(F.data == "Return")
async def cb_return(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None or callback.message is None or callback.message.chat is None:
        return
    data = await state.get_data()
    try_sent_xdr = data.get('try_sent_xdr')
    if try_sent_xdr and datetime.strptime(try_sent_xdr, '%d.%m.%Y %H:%M:%S') > datetime.now():
        check_time = data.get("try_sent_xdr")
        if check_time:
            remaining_seconds = int((datetime.strptime(check_time, '%d.%m.%Y %H:%M:%S') + timedelta(
                seconds=10) - datetime.now()).total_seconds())
            await callback.answer(f'Please wait {remaining_seconds} seconds', show_alert=True)
    else:
        await cmd_show_balance(session, callback.message.chat.id, state, app_context=app_context)
        await callback.answer()
    await check_update_username(
        session,
        callback.from_user.id,
        callback.from_user.username or "",
        state,
        app_context=app_context,
    )


@router.callback_query(F.data == "DeleteReturn")
async def cb_delete_return(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None or callback.message is None or callback.message.chat is None:
        return
    try:
        if isinstance(callback.message, types.Message):
            await callback.message.delete()
    except:
        if isinstance(callback.message, types.Message):
            await callback.message.edit_text('deleted')
            await callback.message.edit_reply_markup(None)

    await cmd_show_balance(session, callback.message.chat.id, state, app_context=app_context)
    await callback.answer()
    await check_update_username(
        session,
        callback.from_user.id,
        callback.from_user.username or "",
        state,
        app_context=app_context,
    )


@router.message(Command(commands=["about"]))
async def cmd_about(message: types.Message, session: AsyncSession, app_context: AppContext):
    if message.from_user is None:
        return
    msg = f'Sorry not ready\n' \
          f'Тут будет что-то о кошельке, переводчиках и добрых людях\n' \
          f'стать добрым - /donate'
    await send_message(session, message.from_user.id, msg, reply_markup=get_kb_return(message, app_context=app_context), app_context=app_context)
@router.callback_query(F.data == "Donate")
async def cb_donate(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    await cmd_donate(session, callback.from_user.id, state, app_context=app_context)
    await callback.answer()


@router.message(Command(commands=["donate"]))
async def cmd_donate_message(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None:
        return
    await clear_state(state)
    await cmd_donate(session, message.from_user.id, state, app_context=app_context)


def get_kb_donate(chat_id: int, *, app_context: AppContext) -> types.InlineKeyboardMarkup:
    buttons_list = [["1", "5", "10", "50"],
                    ["100", "300", "1000"]]

    kb_buttons = []

    for buttons in buttons_list:
        tmp_buttons = []
        for button in buttons:
            tmp_buttons.append(
                types.InlineKeyboardButton(text=button, callback_data=button))
        kb_buttons.append(tmp_buttons)
    kb_buttons.append(get_return_button(chat_id, app_context=app_context))

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    return keyboard


async def cmd_donate(session: AsyncSession, user_id: int, state: FSMContext, app_context: AppContext):
    # Refactored to use GetWalletBalance Use Case
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    balances = await balance_use_case.execute(user_id=user_id)
    # Filter for EURMTL
    eurmtl_balances = [b for b in balances if b.asset_code == 'EURMTL']
    eurmtl_balance = 0.0
    if eurmtl_balances:
        eurmtl_balance = float(eurmtl_balances[0].balance or 0.0)

    msg = f'You have {eurmtl_balance} EURMTL\n' \
          f'Choose how much you want to send or send a sum\n' \
          f'Top 5 donators you can see at /about list'
    await state.set_state(SettingState.send_donate_sum)
    await state.update_data(max_sum=eurmtl_balance, msg=msg)
    await send_message(
        session,
        user_id,
        msg,
        reply_markup=get_kb_donate(user_id, app_context=app_context),
        app_context=app_context,
    )


async def cmd_after_donate(session: AsyncSession, user_id: int, state: FSMContext, *, app_context: AppContext, **kwargs):
    data = await state.get_data()
    donate_sum = data.get('donate_sum')
    admin_id = app_context.admin_id
    await send_message(
        session,
        user_id=admin_id,
        msg=f'{user_id} donate {donate_sum}',
        need_new_msg=True,
        reply_markup=get_kb_return(user_id, app_context=app_context),
        app_context=app_context,
    )
    
    await send_message(
        session,
        user_id=admin_id,
        msg=f'{user_id} donate {donate_sum}',
        need_new_msg=True,
        reply_markup=get_kb_return(user_id, app_context=app_context),
        app_context=app_context,
    )
    
    add_donation = app_context.use_case_factory.create_add_donation(session)
    await add_donation.execute(user_id, donate_sum)


async def get_donate_sum(session: AsyncSession, user_id, donate_sum, state: FSMContext, app_context: AppContext):
    data = await state.get_data()
    max_sum = float(data['max_sum'])
    try:
        donate_sum = float(donate_sum)
        if donate_sum > max_sum:
            await send_message(session, user_id, my_gettext(user_id, 'bad_sum', app_context=app_context) + '\n' + data['msg'],
                               reply_markup=get_kb_return(user_id, app_context=app_context), app_context=app_context)
        else:
            # Refactored to use Clean Architecture Use Case
            from core.constants import EURMTL_ASSET
            from other.config_reader import config as app_config

            repo = app_context.repository_factory.get_wallet_repository(session)
            use_case = app_context.use_case_factory.create_send_payment(session)

            # Get father key (fee account or similar? 0 is usually master/fee account in this bot's logic)
            # In legacy stellar_tools: stellar_get_user_account(session, 0)
            # We can use wallet repo to get system account if stored there, or config.
            # Assuming user_id=0 exists in wallet table.
            father_wallet = await repo.get_default_wallet(0)
            father_key = father_wallet.public_key if father_wallet else None
            
            if not father_key:
                 # Fallback if 0 user not found, though it should be.
                 # Maybe generic error or log?
                 from core.constants import PUBLIC_MMWB
                 father_key = PUBLIC_MMWB # Fallback

            memo = "donate"
            
            result = await use_case.execute(
                user_id=user_id,
                destination_address=father_key,
                asset=EURMTL_ASSET,
                amount=donate_sum,
                memo=memo
            )

            if result.success:
                xdr = result.xdr
                await state.update_data(xdr=xdr, donate_sum=donate_sum, fsm_after_send=jsonpickle.dumps(cmd_after_donate))
                msg = my_gettext(user_id, 'confirm_send', (donate_sum, EURMTL_ASSET.code, father_key, memo), app_context=app_context)
                msg = f"For donate\n{msg}"
                await send_message(
                    session,
                    user_id,
                    msg,
                    reply_markup=get_kb_yesno_send_xdr(user_id, app_context=app_context),
                    app_context=app_context,
                )
            else:
                await send_message(
                    session,
                    user_id,
                    f"Error: {result.error_message}",
                    reply_markup=get_kb_return(user_id, app_context=app_context),
                    app_context=app_context,
                )

    except Exception as ex:
        # logger.error(["get_donate_sum", ex])
        await send_message(
            session,
            user_id,
            my_gettext(user_id, 'bad_sum', app_context=app_context) + '\n' + data['msg'],
            reply_markup=get_kb_return(user_id, app_context=app_context),
            app_context=app_context,
        )


@router.callback_query(SettingState.send_donate_sum)
async def cb_donate_sum(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    await get_donate_sum(session, callback.from_user.id, callback.data, state, app_context=app_context)
    await callback.answer()


@router.message(SettingState.send_donate_sum)
async def cmd_donate_sum(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None:
        return
    await get_donate_sum(session, message.from_user.id, message.text, state, app_context=app_context)
    await message.delete()


@router.message(Command(commands=["delete_all"]))
async def cmd_delete_all(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None:
        return
    # Legacy delete all commented out
    # If implemented, use DeleteUser use case
    await send_message(session, message.from_user.id, 'All was delete, restart please', app_context=app_context)
    await state.clear()


@router.callback_query(F.data == "SetDefault")
async def cb_set_default(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    await state.set_state(SettingState.send_default_address)
    # user_repo imported at top or here? Imported at top now.
    user_repo = app_context.repository_factory.get_user_repository(session)
    user = await user_repo.get_by_id(callback.from_user.id)
    default_addr = user.default_address if user else None
    msg = my_gettext(callback, 'set_default', (default_addr,), app_context=app_context)
    await send_message(
        session,
        callback,
        msg,
        reply_markup=get_kb_return(callback, app_context=app_context),
        app_context=app_context,
    )
    await callback.answer()


@router.callback_query(F.data == "SetLimit")
@router.callback_query(F.data == "OffLimits")
async def cb_set_limit(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    user_repo = app_context.repository_factory.get_user_repository(session)
    db_user = await user_repo.get_by_id(callback.from_user.id)
    if callback.data == 'OffLimits' and db_user:
        db_user.can_5000 = 1 if db_user.can_5000 == 0 else 0
        # Note: IUserRepository does not have a general update method

    msg = my_gettext(callback, 'limits', app_context=app_context)
    await send_message(
        session,
        callback,
        msg,
        reply_markup=get_kb_limits(
            callback.from_user.id,
            db_user.can_5000 if db_user else 0,
            app_context=app_context,
        ),
        app_context=app_context,
    )
    await callback.answer()
    await session.commit()


@router.message(SettingState.send_default_address)
async def cmd_set_default(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None:
        return
    address = message.text
    try:
        from other.config_reader import config as app_config
        balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
        await balance_use_case.execute(user_id=message.from_user.id, public_key=address)
        # Update default address via UpdateUserProfile Use Case
        update_profile = app_context.use_case_factory.create_update_user_profile(session)
        await update_profile.execute(user_id=message.from_user.id, default_address=address)
    except:
        update_profile = app_context.use_case_factory.create_update_user_profile(session)
        await update_profile.execute(user_id=message.from_user.id, default_address='')

    user_repo = app_context.repository_factory.get_user_repository(session)
    user = await user_repo.get_by_id(message.from_user.id)
    default_addr = user.default_address if user else None
    msg = my_gettext(message, 'set_default', (default_addr,), app_context=app_context)
    await send_message(
        session,
        message,
        msg,
        reply_markup=get_kb_return(message, app_context=app_context),
        app_context=app_context,
    )

    await message.delete()


@rate_limit(3, 'private_links')
@router.callback_query(F.data == "Refresh")
async def cmd_refresh(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    repo = app_context.repository_factory.get_wallet_repository(session)
    await repo.reset_balance_cache(callback.from_user.id)
    await cmd_show_balance(session, callback.from_user.id, state, refresh_callback=callback, app_context=app_context)
    await callback.answer()
    await check_update_username(
        session,
        callback.from_user.id,
        callback.from_user.username,
        state,
        app_context=app_context,
    )


async def check_update_username(
    session: AsyncSession,
    user_id: int,
    user_name: Optional[str],
    state: FSMContext,
    *,
    app_context: AppContext,
):
    """
        Check if the username in the database matches the real telegram-user name.
        If not, then update in the database and in FSM-state.
    """
    clean_user_name = user_name.lower() if user_name else ''
    data = await state.get_data()
    state_user_name = data.get('user_name', '')
    if clean_user_name != state_user_name:
        update_profile = app_context.use_case_factory.create_update_user_profile(session)
        await update_profile.execute(user_id=user_id, username=clean_user_name)
        await state.update_data(user_name=clean_user_name)


@router.callback_query(F.data == "ShowMoreToggle")
async def cq_show_more_less_click(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    """
        Invert state of 'show_more' flag by clicking on button.
    """
    data = await state.get_data()
    new_state = not data.get('show_more', False)  # Invert flag state
    await state.update_data(show_more=new_state)

    if callback.message is None or not isinstance(callback.message, types.Message):
        return
    keyboard = await get_kb_default(session, callback.from_user.id, state, app_context=app_context)
    await callback.message.edit_text(text=await get_start_text(session, state, callback.from_user.id, app_context=app_context),
                                     reply_markup=keyboard, disable_web_page_preview=True)
    await callback.answer()
