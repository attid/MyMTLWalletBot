from contextlib import suppress

import jsonpickle
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from loguru import logger
from sqlalchemy.orm import Session
from db.requests import db_user_can_new_free, db_add_wallet
from keyboards.common_keyboards import get_kb_return, get_return_button
from routers.sign import cmd_ask_pin, PinState
from routers.start_msg import cmd_show_balance, cmd_info_message
from other.aiogram_tools import send_message, my_gettext
from other.stellar_tools import stellar_create_new, stellar_save_new, \
    stellar_save_ro, async_stellar_send, new_wallet_lock


class StateAddWallet(StatesGroup):
    sending_private = State()
    sending_public = State()


router = Router()
router.message.filter(F.chat.type == "private")


@router.callback_query(F.data == "AddNew")
async def cmd_add_new(callback: types.CallbackQuery, session: Session):
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_have_key'),
                                    callback_data="AddWalletHaveKey")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_get_free'),
                                    callback_data="AddWalletNewKey")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_read_only'),
                                    callback_data="AddWalletReadOnly")],
        [types.InlineKeyboardButton(text='Create new TON wallet',
                                    callback_data="AddTonWallet")],
        get_return_button(callback)
    ]
    msg = my_gettext(callback, 'create_msg')
    await send_message(session, callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "AddWalletHaveKey")
async def cq_add(callback: types.CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'send_key')
    await state.update_data(msg=msg)
    await state.set_state(StateAddWallet.sending_private)
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback))


@router.message(StateAddWallet.sending_private)
async def cmd_sending_private(message: types.Message, state: FSMContext, session: Session):
    try:
        arg = message.text.split()
        if len(arg) == 2:
            public_key = stellar_save_new(session, message.from_user.id, message.from_user.username, arg[0], False,
                                          arg[1])
        else:
            public_key = stellar_save_new(session, message.from_user.id, message.from_user.username, arg[0], False)
        await state.update_data(public_key=public_key)
        await state.set_state(None)
        await cmd_show_add_wallet_choose_pin(session, message.chat.id, state,
                                             my_gettext(message, 'for_address', (public_key,)))
        await message.delete()
    except Exception as ex:
        logger.info(ex)
        data = await state.get_data()
        await send_message(session, message, my_gettext(message, 'bad_key') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))


@router.callback_query(F.data == "AddWalletNewKey")
async def cq_add(callback: types.CallbackQuery, session: Session, state: FSMContext):
    if db_user_can_new_free(session, callback.from_user.id):
        msg = my_gettext(callback, "try_send")
        waiting_count = new_wallet_lock.waiting_count()
        if waiting_count > 0:
            await cmd_info_message(session, callback.message.chat.id,
                                   f'Please wait, your position in the queue is {waiting_count}.')

        async with new_wallet_lock:
            xdr = await stellar_create_new(session, callback.from_user.id, callback.from_user.username)
            await cmd_info_message(session, callback.message.chat.id, msg)
            await async_stellar_send(xdr)

        await cmd_info_message(session, callback, my_gettext(callback, 'send_good'))
        with suppress(TelegramBadRequest):
            await callback.answer()
        data = await state.get_data()
        fsm_after_send = data.get('fsm_after_send')
        if fsm_after_send:
            fsm_after_send = jsonpickle.loads(fsm_after_send)
            await fsm_after_send(session, callback.from_user.id, state)
    else:
        await callback.answer(my_gettext(callback.message.chat.id, "max_wallets"), show_alert=True)


async def cmd_show_add_wallet_choose_pin(session: Session, user_id: int, state: FSMContext, msg=''):
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_pin'),
                                    callback_data="PIN")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_password'),
                                    callback_data="Password")],
        [types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_no_password'),
                                    callback_data="NoPassword"),
         ]
    ]

    msg = msg + my_gettext(user_id, 'choose_protect')
    await send_message(session, user_id, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
                       parse_mode='HTML')


@router.callback_query(F.data == "AddWalletReadOnly")
async def cq_add_read_only(callback: types.CallbackQuery, state: FSMContext, session: Session):
    msg = my_gettext(callback, 'add_read_only')
    await state.update_data(msg=msg)
    await state.set_state(StateAddWallet.sending_public)
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback))


@router.message(StateAddWallet.sending_public)
async def cmd_sending_public(message: types.Message, state: FSMContext, session: Session):
    try:
        # await stellar_get_balances(session, message.from_user.id, public_key=message.text)
        await state.update_data(public_key=message.text)
        await state.set_state(None)

        stellar_save_ro(session, message.from_user.id, message.from_user.username, public_key=message.text)

        await cmd_show_balance(session, message.from_user.id, state)
        await message.delete()
    except Exception as ex:
        logger.info(ex)
        data = await state.get_data()
        await send_message(session, message, my_gettext(message, 'bad_key') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))


@router.callback_query(F.data == "PIN")
async def cq_add_read_only(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await state.set_state(PinState.set_pin)
    await state.update_data(pin_type=1)
    await cmd_ask_pin(session, callback.message.chat.id, state)


@router.callback_query(F.data == "Password")
async def cq_add_password(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await state.update_data(pin_type=2)
    await state.set_state(PinState.ask_password_set)
    await send_message(session, callback, my_gettext(callback, 'send_password'),
                       reply_markup=get_kb_return(callback))


@router.callback_query(F.data == "NoPassword")
async def cq_add_read_only(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await state.update_data(pin_type=0)
    await cmd_show_balance(session, callback.from_user.id, state)


@router.callback_query(F.data == "AddTonWallet")
async def cq_add(callback: types.CallbackQuery, session: Session, state: FSMContext):
    if db_user_can_new_free(session, callback.from_user.id):
        from services.ton_service import TonService

        ton_service = TonService()
        ton_service.create_wallet()
        db_add_wallet(session=session, user_id=callback.from_user.id,
                      public_key=ton_service.wallet.address.to_str(is_bounceable=False), secret_key='TON', i_free_wallet=1,
                      seed_key=ton_service.mnemonic)

        await cmd_info_message(session, callback, my_gettext(callback, 'send_good'))
    else:
        await callback.answer(my_gettext(callback.message.chat.id, "max_wallets"), show_alert=True)
