from aiogram import Router, types
from aiogram.filters import Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from keyboards.common_keyboards import get_kb_return, get_return_button
from routers.sign import cmd_ask_pin, PinState
from routers.start_msg import cmd_show_balance, cmd_info_message
from utils.aiogram_utils import send_message, my_gettext, logger
from utils.stellar_utils import stellar_can_new, stellar_create_new, stellar_save_new, \
    stellar_get_balances, stellar_save_ro, async_stellar_send


class StateAddWallet(StatesGroup):
    sending_private = State()
    sending_public = State()


router = Router()


@router.callback_query(Text(text=["AddNew"]))
async def cmd_add_new(callback: types.CallbackQuery, state: FSMContext):
    buttons = [
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_have_key'),
                                    callback_data="AddWalletHaveKey")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_get_free'),
                                    callback_data="AddWalletNewKey")],
        [types.InlineKeyboardButton(text=my_gettext(callback, 'kb_read_only'),
                                    callback_data="AddWalletReadOnly")],
        get_return_button(callback)
    ]
    msg = my_gettext(callback, 'create_msg')
    await send_message(callback, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(Text(text=["AddWalletHaveKey"]))
async def cq_add(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'send_key')
    await state.update_data(msg=msg)
    await state.set_state(StateAddWallet.sending_private)
    await send_message(callback, msg, reply_markup=get_kb_return(callback))


@router.message(StateAddWallet.sending_private)
async def cmd_sending_private(message: types.Message, state: FSMContext):
    try:
        arg = message.text.split()
        if len(arg) == 2:
            public_key = stellar_save_new(message.from_user.id, message.from_user.username, arg[0], False, arg[1])
        else:
            public_key = stellar_save_new(message.from_user.id, message.from_user.username, arg[0], False)
        await state.update_data(public_key=public_key)
        await state.set_state(None)
        await cmd_show_add_wallet_choose_pin(message.chat.id, state,
                                             my_gettext(message, 'for_address', (public_key,)))
        await message.delete()
    except Exception as ex:
        logger.info(ex)
        data = await state.get_data()
        await send_message(message, my_gettext(message, 'bad_key') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))


@router.callback_query(Text(text=["AddWalletNewKey"]))
async def cq_add(callback: types.CallbackQuery, state: FSMContext):
    if stellar_can_new(callback.from_user.id):
        xdr = stellar_create_new(callback.from_user.id, callback.from_user.username)
        await cmd_info_message(callback.message.chat.id, my_gettext(callback, "try_send"), state)
        #save_xdr_to_send(callback.from_user.id, xdr)
        await async_stellar_send(xdr)
        await cmd_info_message(callback, my_gettext(callback, 'send_good'), state)
        await callback.answer()
    else:
        await callback.answer(my_gettext(callback.message.chat.id, "max_wallets"), show_alert=True)


async def cmd_show_add_wallet_choose_pin(user_id: int, state: FSMContext, msg=''):
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
    await send_message(user_id, msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
                       parse_mode='MARKDOWN')


@router.callback_query(Text(text=["AddWalletReadOnly"]))
async def cq_add_read_only(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, 'add_read_only')
    await state.update_data(msg=msg)
    await state.set_state(StateAddWallet.sending_public)
    await send_message(callback, msg, reply_markup=get_kb_return(callback))


@router.message(StateAddWallet.sending_public)
async def cmd_sending_private(message: types.Message, state: FSMContext):
    try:
        stellar_get_balances(message.from_user.id, public_key=message.text)
        await state.update_data(public_key=message.text)
        await state.set_state(None)

        stellar_save_ro(message.from_user.id, message.from_user.username, public_key=message.text)

        await cmd_show_balance(message.from_user.id, state)
        await message.delete()
    except Exception as ex:
        logger.info(ex)
        data = await state.get_data()
        await send_message(message, my_gettext(message, 'bad_key') + '\n' + data['msg'],
                           reply_markup=get_kb_return(message))


@router.callback_query(Text(text=["PIN"]))
async def cq_add_read_only(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PinState.set_pin)
    await state.update_data(pin_type=1)
    await cmd_ask_pin(callback.message.chat.id, state)


@router.callback_query(Text(text=["Password"]))
async def cq_add_password(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(pin_type=2)
    await state.set_state(PinState.ask_password_set)
    await send_message(callback, my_gettext(callback, 'send_password'),
                       reply_markup=get_kb_return(callback))


@router.callback_query(Text(text=["NoPassword"]))
async def cq_add_read_only(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(pin_type=0)
    await cmd_show_balance(callback.from_user.id, state)
