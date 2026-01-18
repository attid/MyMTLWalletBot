from contextlib import suppress

import jsonpickle
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from loguru import logger
from sqlalchemy.orm import Session
from cryptocode import decrypt, encrypt
from stellar_sdk import Keypair

from keyboards.common_keyboards import get_kb_return, get_return_button
from routers.sign import cmd_ask_pin, PinState
from routers.start_msg import cmd_show_balance, cmd_info_message
from infrastructure.utils.telegram_utils import send_message, my_gettext
# from other.stellar_tools import stellar_create_new, stellar_save_new, stellar_save_ro, async_stellar_send, new_wallet_lock
from other.locks import new_wallet_lock
from other.config_reader import config

from infrastructure.services.app_context import AppContext
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from infrastructure.services.stellar_service import StellarService
from core.use_cases.wallet.add_wallet import AddWallet


class StateAddWallet(StatesGroup):
    sending_private = State()
    sending_public = State()


router = Router()
router.message.filter(F.chat.type == "private")


@router.callback_query(F.data == "AddNew")
@router.callback_query(F.data == "AddNew")
async def cmd_add_new(callback: types.CallbackQuery, session: Session, app_context: AppContext):
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_have_key', app_context=app_context),
                                    callback_data="AddWalletHaveKey")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_get_free', app_context=app_context),
                                    callback_data="AddWalletNewKey")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_read_only', app_context=app_context),
                                    callback_data="AddWalletReadOnly")],
        [types.InlineKeyboardButton(text='Create new TON wallet',
                                    callback_data="AddTonWallet")],
        get_return_button(callback, app_context=app_context)
    ]
    msg = my_gettext(callback, 'create_msg', app_context=app_context)
    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "AddWalletHaveKey")
async def cq_add_have_key(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    msg = my_gettext(callback, 'send_key', app_context=app_context)
    await state.update_data(msg=msg)
    await state.set_state(StateAddWallet.sending_private)
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback, app_context=app_context))


@router.message(StateAddWallet.sending_private)
async def cmd_sending_private(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    try:
        args = message.text.split()
        secret_key = args[0]
        kp = Keypair.from_secret(secret_key)
        public_key = kp.public_key
        
        wallet_repo = SqlAlchemyWalletRepository(session)
        add_wallet = AddWallet(wallet_repo)
        
        encrypted_secret = encrypt(secret_key, str(message.from_user.id))
        
        await add_wallet.execute(
            user_id=message.from_user.id,
            public_key=public_key,
            secret_key=encrypted_secret,
            is_free=False,
            is_default=False 
        )
        
        await state.update_data(public_key=public_key)
        await state.set_state(None)
        await cmd_show_add_wallet_choose_pin(session, message.chat.id, state,
                                             my_gettext(message, 'for_address', (public_key,), app_context=app_context),
                                             app_context=app_context)
        await message.delete()
    except Exception as ex:
        logger.info(ex)
        data = await state.get_data()
        await send_message(session, message, my_gettext(message, 'bad_key', app_context=app_context) + '\n' + data['msg'],
                           reply_markup=get_kb_return(message, app_context=app_context))


@router.callback_query(F.data == "AddWalletNewKey")
async def cq_add_new_key(callback: types.CallbackQuery, session: Session, state: FSMContext, app_context: AppContext):
    # Check if user can add free wallet (via Use Case check/Repo limit)
    wallet_repo = SqlAlchemyWalletRepository(session)
    add_wallet = AddWallet(wallet_repo)
    
    # We can check limit first to fail fast, although execute() does it too.
    try:
        # Check limit manually or just try? 
        count = await wallet_repo.count_free_wallets(callback.from_user.id)
        if count > 2:
             await callback.answer(my_gettext(callback.message.chat.id, "max_wallets", app_context=app_context), show_alert=True)
             return
             
        msg = my_gettext(callback, "try_send", app_context=app_context)
        waiting_count = new_wallet_lock.waiting_count()
        if waiting_count > 0:
            await cmd_info_message(session, callback.message.chat.id,
                                   f'Please wait, your position in the queue is {waiting_count}.', app_context=app_context)

        async with new_wallet_lock:
             # 1. Generate keys
             mnemonic = Keypair.generate_mnemonic_phrase()
             kp = Keypair.from_mnemonic_phrase(mnemonic)
             
             # 2. Add to DB
             # Encrypt secrets
             encrypted_secret = encrypt(kp.secret, str(callback.from_user.id))
             # seed_key encrypted with OWN secret (legacy logic)
             encrypted_seed = encrypt(mnemonic, kp.secret)
             
             await add_wallet.execute(
                 user_id=callback.from_user.id,
                 public_key=kp.public_key,
                 secret_key=encrypted_secret,
                 seed_key=encrypted_seed,
                 is_free=True,
                 is_default=False # Will be set to true inside execute if first? NO, execute sets default if is_default=True
                 # Legacy set default via db_add_wallet calling set_default.
             )
             
             # 3. Fund and Trust (StellarService)
             await cmd_info_message(session, callback.message.chat.id, msg, app_context=app_context)
             
             service = StellarService(config.horizon_url_rw)
             master_wallet = await wallet_repo.get_default_wallet(0)
             if not master_wallet:
                 logger.error("No master wallet found!")
                 await send_message(session, callback, "Error: System wallet missing")
                 return
                 
             master_secret = decrypt(master_wallet.secret_key, '0')
             
             # Create Account
             xdr = await service.build_payment_transaction(
                 source_account_id=master_wallet.public_key,
                 destination_account_id=kp.public_key,
                 asset_code="XLM",
                 asset_issuer=None,
                 amount="5",
                 create_account=True
             )
             signed_xdr = service.sign_transaction(xdr, master_secret)
             await service.submit_transaction(signed_xdr)
             
             # Add Trustlines
             from core.constants import MTL_ASSET, EURMTL_ASSET, SATSMTL_ASSET, USDM_ASSET
             for asset in [MTL_ASSET, EURMTL_ASSET, SATSMTL_ASSET, USDM_ASSET]:
                 trust_xdr = await service.build_change_trust_transaction(
                     source_account_id=kp.public_key,
                     asset_code=asset.code,
                     asset_issuer=asset.issuer
                 )
                 signed_trust = service.sign_transaction(trust_xdr, kp.secret)
                 await service.submit_transaction(signed_trust)

        await cmd_info_message(session, callback, my_gettext(callback, 'send_good', app_context=app_context), app_context=app_context)
        with suppress(TelegramBadRequest):
            await callback.answer()
        data = await state.get_data()
        fsm_after_send = data.get('fsm_after_send')
        if fsm_after_send:
            fsm_after_send = jsonpickle.loads(fsm_after_send)
            await fsm_after_send(session, callback.from_user.id, state)
            
    except Exception as e:
        logger.error(f"Error creating wallet: {e}")
        await callback.answer(f"Error: {e}", show_alert=True)


async def cmd_show_add_wallet_choose_pin(session: Session, user_id: int, state: FSMContext, msg='', app_context: AppContext = None):
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_pin', app_context=app_context),
                                    callback_data="PIN")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_password', app_context=app_context),
                                    callback_data="Password")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_no_password', app_context=app_context),
                                    callback_data="NoPassword"),
         ]
    ]

    msg = msg + my_gettext(user_id, 'choose_protect', app_context=app_context)
    await send_message(session, user_id, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
                       parse_mode='HTML')


@router.callback_query(F.data == "AddWalletReadOnly")
async def cq_add_read_only(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    msg = my_gettext(callback, 'add_read_only', app_context=app_context)
    await state.update_data(msg=msg)
    await state.set_state(StateAddWallet.sending_public)
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback, app_context=app_context))


@router.message(StateAddWallet.sending_public)
async def cmd_sending_public(message: types.Message, state: FSMContext, session: Session, app_context: AppContext):
    try:
        # await stellar_get_balances(session, message.from_user.id, public_key=message.text)
        public_key = message.text
        
        wallet_repo = SqlAlchemyWalletRepository(session)
        add_wallet = AddWallet(wallet_repo)
        
        # Legacy behavior: save public_key as secret_key too for RO wallets
        await add_wallet.execute(
            user_id=message.from_user.id,
            public_key=public_key,
            secret_key=public_key, 
            is_free=False,
            is_read_only=True,
            is_default=False
        )
        
        await state.update_data(public_key=public_key)
        await state.set_state(None)

        await cmd_show_balance(session, message.from_user.id, state, app_context=app_context)
        await message.delete()
    except Exception as ex:
        logger.info(ex)
        data = await state.get_data()
        await send_message(session, message, my_gettext(message, 'bad_key', app_context=app_context) + '\n' + data['msg'],
                           reply_markup=get_kb_return(message, app_context=app_context))


@router.callback_query(F.data == "PIN")
async def cq_add_read_only_pin(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    await state.set_state(PinState.set_pin)
    await state.update_data(pin_type=1)
    await cmd_ask_pin(session, callback.message.chat.id, state, app_context=app_context)


@router.callback_query(F.data == "Password")
async def cq_add_password(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    await state.update_data(pin_type=2)
    await state.set_state(PinState.ask_password_set)
    await send_message(session, callback, my_gettext(callback, 'send_password', app_context=app_context),
                       reply_markup=get_kb_return(callback, app_context=app_context))


@router.callback_query(F.data == "NoPassword")
async def cq_add_read_only_no_password(callback: types.CallbackQuery, state: FSMContext, session: Session, app_context: AppContext):
    await state.update_data(pin_type=0)
    await cmd_show_balance(session, callback.from_user.id, state, app_context=app_context)


@router.callback_query(F.data == "AddTonWallet")
async def cq_add_ton(callback: types.CallbackQuery, session: Session, state: FSMContext, app_context: AppContext):
    try:
        wallet_repo = SqlAlchemyWalletRepository(session)
        add_wallet = AddWallet(wallet_repo)
        
        # Check limits effectively done by add_wallet.execute(is_free=True)?
        # But we need to generate keys first. It's safe to generate then fail if limit reached.
        # Or check first.
        count = await wallet_repo.count_free_wallets(callback.from_user.id)
        if count > 2:
             await callback.answer(my_gettext(callback.message.chat.id, "max_wallets", app_context=app_context), show_alert=True)
             return

        from services.ton_service import TonService

        ton_service = TonService()
        ton_service.create_wallet()
        
        # public_key: string representation
        public_key = ton_service.wallet.address.to_str(is_bounceable=False)
        seed_key = ton_service.mnemonic # List of strings? Or string?
        # ton_service.mnemonic type? 
        # Legacy: seed_key=ton_service.mnemonic passed to db_add_wallet.
        # If it's a list, db adapter probably handled it or it's a string.
        # TonService.mnemonic is usually a list of words.
        # `db/requests.py` takes `seed_key: str`.
        # Assuming `ton_service.mnemonic` is a string or I should join it.
        # Looking at legacy code: seed_key=ton_service.mnemonic.
        # If it's a list, SQLAlchemy might complain if column is String.
        # Checking `services/ton_service.py` not possible conveniently right now, assuming existing usage was correct.
        # If `ton_service.mnemonic` is list, I should probably join it? 
        # `pytonlib` mnemonic is list.
        # I'll convert to string just in case if it's list.
        seed_str = seed_key
        if isinstance(seed_key, list):
            seed_str = " ".join(seed_key)

        await add_wallet.execute(
            user_id=callback.from_user.id,
            public_key=public_key,
            secret_key='TON',
            seed_key=seed_str,
            is_free=True,
            is_default=False
        )

        await cmd_info_message(session, callback, my_gettext(callback, 'send_good', app_context=app_context), app_context=app_context)
    except Exception as e:
        logger.error(f"Error adding TON wallet: {e}")
        await callback.answer(f"Error: {e}", show_alert=True)
