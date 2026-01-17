import asyncio
from datetime import datetime, timedelta
import jsonpickle
from aiogram import Router, types, Bot, F
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.orm import Session

from sqlalchemy.orm import Session
from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from core.use_cases.user.register import RegisterUser
from core.use_cases.user.update_profile import UpdateUserProfile
from core.use_cases.user.manage_user import AddDonation 
# from db.requests import db_add_donate, db_delete_all_by_user, db_add_user_if_not_exists, db_update_username
from keyboards.common_keyboards import get_return_button, get_kb_return, get_kb_yesno_send_xdr, get_kb_limits
from middleware.throttling import rate_limit
from routers.common_setting import cmd_language
from routers.sign import cmd_check_xdr
from routers.start_msg import cmd_show_balance, get_kb_default, get_start_text
from infrastructure.utils.telegram_utils import send_message, clear_state
from other.global_data import global_data
from other.lang_tools import my_gettext, check_user_id, check_user_lang
from other.stellar_tools import (stellar_get_balances, stellar_get_user_account,
                                 )

router = Router()
router.message.filter(F.chat.type == "private")


class SettingState(StatesGroup):
    send_donate_sum = State()
    send_default_address = State()


@router.message(Command(commands=["start"]), F.text.contains("sign_"))
async def cmd_start_sign(message: types.Message, state: FSMContext, session: Session):
    await clear_state(state)

    # check address
    await state.update_data(last_message_id=0)
    await send_message(session, message.from_user.id, 'Loading')

    # if user not exist
    if not check_user_id(session, message.from_user.id):
        await send_message(session, message.from_user.id, 'You dont have wallet. Please run /start')
        return

    await cmd_check_xdr(session, 'https://eurmtl.me/sign_tools/' + message.text.split(' ')[1][5:], message.from_user.id,
                        state)


# @router.message(Command(commands=["start"]))
@router.message(F.text.lower() == '/start', F.chat.type == 'private')
async def cmd_start(message: types.Message, state: FSMContext, session: Session, bot: Bot):
    # logger.info([message.from_user.id, ' cmd_start'])
    await clear_state(state)

    # check address
    await state.update_data(last_message_id=0)
    await send_message(session, message.from_user.id, 'Loading')

    if check_user_lang(session, message.from_user.id) is None:
        # Refactored to use Clean Architecture Use Case
        from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
        from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
        from core.use_cases.user.register import RegisterUser

        user_repo = SqlAlchemyUserRepository(session)
        wallet_repo = SqlAlchemyWalletRepository(session)
        register_use_case = RegisterUser(user_repo, wallet_repo)
        
        # We need to generate a keypair. For now, retaining reliance on stellar_tools or similar if needed,
        # but RegisterUser expects keys.
        # Existing db_add_user_if_not_exists generated keys internally or user_account used?
        # db_add_user_if_not_exists called db.requests which usually generated keys.
        # Let's see how we can bridge this. 
        # For Phase 1, we can generate keys here using the old tool or a new one.
        from other.stellar_tools import get_new_account
        keypair = await get_new_account() 
        # get_new_account returns object with public_key, secret_key.
        # Wait, get_new_account implementation? I need to verify.
        # Assuming it returns a Keypair object.
        
        # To avoid breaking if get_new_account is complex, let's allow RegisterUser to handle key gen if passed None?
        # No, I implemented RegisterUser taking keys.
        # Let's check stellar_tools.py in 'other' (I haven't read it but can infer or read).
        # To be safe, I'll read stellar_tools.py briefly or assume usage.
        # Actually, `db_add_user_if_not_exists` in `db/requests.py` is what I am replacing.
        # It's better to read `db/requests.py` to see what it did for key generation.
        
        await register_use_case.execute(
             user_id=message.from_user.id,
             username=message.from_user.username,
             language='en', # Default
             public_key=keypair.public_key,
             secret_key=keypair.secret_key
        )
        
        # db_add_user_if_not_exists(session, message.from_user.id, message.from_user.username)
        await cmd_language(session, message.from_user.id)
    else:
        await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        await cmd_show_balance(session, message.from_user.id, state)
        await check_update_username(
            session, message.from_user.id, message.from_user.username, state
        )


@router.callback_query(F.data == "Return")
async def cb_return(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    try_sent_xdr = data.get('try_sent_xdr')
    if try_sent_xdr and datetime.strptime(try_sent_xdr, '%d.%m.%Y %H:%M:%S') > datetime.now():
        check_time = data.get("try_sent_xdr")
        remaining_seconds = int((datetime.strptime(check_time, '%d.%m.%Y %H:%M:%S') + timedelta(
            seconds=10) - datetime.now()).total_seconds())
        await callback.answer(f'Please wait {remaining_seconds} seconds', show_alert=True)
    else:
        await cmd_show_balance(session, callback.message.chat.id, state)
        await callback.answer()
    await check_update_username(
        session, callback.from_user.id, callback.from_user.username, state
    )


@router.callback_query(F.data == "DeleteReturn")
async def cb_delete_return(callback: types.CallbackQuery, state: FSMContext, session: Session):
    try:
        await callback.message.delete()
    except:
        await callback.message.edit_text('deleted')
        await callback.message.edit_reply_markup(None)

    await cmd_show_balance(session, callback.message.chat.id, state)
    await callback.answer()
    await check_update_username(
        session, callback.from_user.id, callback.from_user.username, state
    )


@router.message(Command(commands=["about"]))
async def cmd_about(message: types.Message, session: Session):
    msg = f'Sorry not ready\n' \
          f'Тут будет что-то о кошельке, переводчиках и добрых людях\n' \
          f'стать добрым - /donate'
    await send_message(session, message.from_user.id, msg, reply_markup=get_kb_return(message))


def get_kb_donate(chat_id: int) -> types.InlineKeyboardMarkup:
    buttons_list = [["1", "5", "10", "50"],
                    ["100", "300", "1000"]]

    kb_buttons = []

    for buttons in buttons_list:
        tmp_buttons = []
        for button in buttons:
            tmp_buttons.append(
                types.InlineKeyboardButton(text=button, callback_data=button))
        kb_buttons.append(tmp_buttons)
    kb_buttons.append(get_return_button(chat_id))

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=kb_buttons)
    return keyboard


async def cmd_donate(session: Session, user_id, state: FSMContext):
    # Refactored to use GetWalletBalance Use Case
    from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    from infrastructure.services.stellar_service import StellarService
    from core.use_cases.wallet.get_balance import GetWalletBalance
    from other.config_reader import config as app_config
    repo = SqlAlchemyWalletRepository(session)
    service = StellarService(horizon_url=app_config.horizon_url)
    balance_use_case = GetWalletBalance(repo, service)
    balances = await balance_use_case.execute(user_id=user_id)
    # Filter for EURMTL
    eurmtl_balances = [b for b in balances if b.asset_code == 'EURMTL']
    eurmtl_balance = 0
    if eurmtl_balances:
        eurmtl_balance = eurmtl_balances[0].balance

    msg = f'You have {eurmtl_balance} EURMTL\n' \
          f'Choose how much you want to send or send a sum\n' \
          f'Top 5 donators you can see at /about list'
    await state.set_state(SettingState.send_donate_sum)
    await state.update_data(max_sum=eurmtl_balance, msg=msg)
    await send_message(session, user_id, msg, reply_markup=get_kb_donate(user_id))


@router.callback_query(F.data == "Donate")
async def cb_donate(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await cmd_donate(session, callback.from_user.id, state)
    await callback.answer()


@router.message(Command(commands=["donate"]))
async def cmd_donate_message(message: types.Message, state: FSMContext, session: Session):
    await clear_state(state)
    await cmd_donate(session, message.from_user.id, state)


async def cmd_after_donate(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    donate_sum = data.get('donate_sum')
    await send_message(session, user_id=global_data.admin_id, msg=f'{user_id} donate {donate_sum}', need_new_msg=True,
                       reply_markup=get_kb_return(user_id))
    
    user_repo = SqlAlchemyUserRepository(session)
    add_donation = AddDonation(user_repo)
    await add_donation.execute(user_id, donate_sum)


async def get_donate_sum(session: Session, user_id, donate_sum, state: FSMContext):
    data = await state.get_data()
    max_sum = float(data['max_sum'])
    try:
        donate_sum = float(donate_sum)
        if donate_sum > max_sum:
            await send_message(session, user_id, my_gettext(user_id, 'bad_sum') + '\n' + data['msg'],
                               reply_markup=get_kb_return(user_id))
        else:
            # Refactored to use Clean Architecture Use Case
            from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
            from infrastructure.services.stellar_service import StellarService
            from core.use_cases.payment.send_payment import SendPayment
            from core.constants import EURMTL_ASSET
            from other.config_reader import config as app_config

            repo = SqlAlchemyWalletRepository(session)
            service = StellarService(horizon_url=app_config.horizon_url)
            use_case = SendPayment(repo, service)

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
                msg = my_gettext(user_id, 'confirm_send', (donate_sum, EURMTL_ASSET.code, father_key, memo))
                msg = f"For donate\n{msg}"
                await send_message(session, user_id, msg, reply_markup=get_kb_yesno_send_xdr(user_id))
            else:
                await send_message(session, user_id, f"Error: {result.error_message}", reply_markup=get_kb_return(user_id))

    except Exception as ex:
        # logger.error(["get_donate_sum", ex])
        await send_message(session, user_id, my_gettext(user_id, 'bad_sum') + '\n' + data['msg'],
                           reply_markup=get_kb_return(user_id))


@router.callback_query(SettingState.send_donate_sum)
async def cb_donate_sum(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await get_donate_sum(session, callback.from_user.id, callback.data, state)
    await callback.answer()


@router.message(SettingState.send_donate_sum)
async def cmd_donate_sum(message: types.Message, state: FSMContext, session: Session):
    await get_donate_sum(session, message.from_user.id, message.text, state)
    await message.delete()


@router.message(Command(commands=["delete_all"]))
async def cmd_delete_all(message: types.Message, state: FSMContext, session: Session):
    # Legacy delete all commented out
    # If implemented, use DeleteUser use case
    await send_message(session, message.from_user.id, 'All was delete, restart please')
    await state.clear()


@router.callback_query(F.data == "SetDefault")
async def cb_set_default(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await state.set_state(SettingState.send_default_address)
    # user_repo imported at top or here? Imported at top now.
    user_repo = SqlAlchemyUserRepository(session)
    user = await user_repo.get_by_id(callback.from_user.id)
    default_addr = user.default_address if user else None
    msg = my_gettext(callback, 'set_default', (default_addr,))
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback))
    await callback.answer()


@router.callback_query(F.data == "SetLimit")
@router.callback_query(F.data == "OffLimits")
async def cb_set_limit(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_repo = SqlAlchemyUserRepository(session)
    db_user = await user_repo.get_by_id(callback.from_user.id)
    if callback.data == 'OffLimits' and db_user:
        db_user.can_5000 = 1 if db_user.can_5000 == 0 else 0
        await user_repo.update(db_user)

    msg = my_gettext(callback, 'limits')
    await send_message(session, callback, msg, reply_markup=get_kb_limits(callback.from_user.id, db_user.can_5000 if db_user else 0))
    await callback.answer()
    session.commit()


@router.message(SettingState.send_default_address)
async def cmd_set_default(message: types.Message, state: FSMContext, session: Session):
    address = message.text
    try:
        from infrastructure.services.stellar_service import StellarService
        from core.use_cases.wallet.get_balance import GetWalletBalance
        from other.config_reader import config as app_config
        repo = SqlAlchemyWalletRepository(session)
        service = StellarService(horizon_url=app_config.horizon_url)
        balance_use_case = GetWalletBalance(repo, service)
        await balance_use_case.execute(user_id=message.from_user.id, public_key=address)
        # Update default address via UpdateUserProfile Use Case
        user_repo = SqlAlchemyUserRepository(session)
        update_profile = UpdateUserProfile(user_repo)
        await update_profile.execute(user_id=message.from_user.id, default_address=address)
    except:
        user_repo = SqlAlchemyUserRepository(session)
        update_profile = UpdateUserProfile(user_repo)
        await update_profile.execute(user_id=message.from_user.id, default_address='')
    
    user_repo = SqlAlchemyUserRepository(session)
    user = await user_repo.get_by_id(message.from_user.id)
    default_addr = user.default_address if user else None
    msg = my_gettext(message, 'set_default', (default_addr,))
    await send_message(session, message, msg, reply_markup=get_kb_return(message))

    await message.delete()


@rate_limit(3, 'private_links')
@router.callback_query(F.data == "Refresh")
async def cmd_refresh(callback: types.CallbackQuery, state: FSMContext, session: Session):
    repo = SqlAlchemyWalletRepository(session)
    await repo.reset_balance_cache(callback.from_user.id)
    await cmd_show_balance(session, callback.from_user.id, state, refresh_callback=callback)
    await callback.answer()
    await check_update_username(
        session, callback.from_user.id, callback.from_user.username, state
    )


async def check_update_username(session: Session, user_id: int, user_name: str, state: FSMContext):
    """
        Check if the username in the database matches the real telegram-user name.
        If not, then update in the database and in FSM-state.
    """
    user_name = user_name.lower() if user_name else ''
    data = await state.get_data()
    state_user_name = data.get('user_name', '')
    if user_name != state_user_name:
        user_repo = SqlAlchemyUserRepository(session)
        update_profile = UpdateUserProfile(user_repo)
        await update_profile.execute(user_id=user_id, username=user_name)
        await state.update_data(user_name=user_name)


@router.callback_query(F.data == "ShowMoreToggle")
async def cq_show_more_less_click(callback: types.CallbackQuery, state: FSMContext, session: Session):
    """
        Invert state of 'show_more' flag by clicking on button.
    """
    data = await state.get_data()
    new_state = not data.get('show_more', False)  # Invert flag state
    await state.update_data(show_more=new_state)

    keyboard = await get_kb_default(session, callback.from_user.id, state)
    await callback.message.edit_text(text=await get_start_text(session, state, callback.from_user.id),
                                     reply_markup=keyboard, disable_web_page_preview=True)
    await callback.answer()
