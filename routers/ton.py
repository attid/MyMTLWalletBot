from typing import Union

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from loguru import logger
from sqlalchemy.orm import Session

from db.requests import db_get_default_wallet
from keyboards.common_keyboards import get_kb_return
from middleware.throttling import rate_limit
from other.aiogram_tools import send_message, clear_state, get_user_id
from services.ton_service import TonService


class StateSendTon(StatesGroup):
    sending_for = State()
    sending_sum = State()
    sending_confirmation = State()

class StateSendTonUSDT(StatesGroup):
    sending_for = State()
    sending_sum = State()
    sending_confirmation = State()


router = Router()

def get_kb_ton_yesno(user_id: Union[types.CallbackQuery, types.Message, int]) -> types.InlineKeyboardMarkup:
    user_id = get_user_id(user_id)

    buttons = [
        [types.InlineKeyboardButton(text="Yes", callback_data="ton_yes")],
        [types.InlineKeyboardButton(text="No", callback_data="ton_no")]
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

@rate_limit(3, 'private_links')
@router.callback_query(F.data == "SendTon")
async def cmd_send_ton_start(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await clear_state(state)
    await send_message(session, callback.from_user.id, "Enter recipient's address:", reply_markup=get_kb_return(callback.from_user.id))
    await state.set_state(StateSendTon.sending_for)
    await callback.answer()


@router.message(StateSendTon.sending_for)
async def cmd_send_ton_address(message: types.Message, state: FSMContext, session: Session):
    address = message.text
    # Basic address validation
    if len(address) != 48:
        await send_message(session, message.from_user.id, "Invalid address. Please enter a valid TON address.", reply_markup=get_kb_return(message.from_user.id))
        return

    await state.update_data(recipient_address=address)
    await send_message(session, message.from_user.id, "Enter amount to send:", reply_markup=get_kb_return(message.from_user.id))
    await state.set_state(StateSendTon.sending_sum)
    await message.delete()


@router.message(StateSendTon.sending_sum)
async def cmd_send_ton_sum(message: types.Message, state: FSMContext, session: Session):
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await send_message(session, message.from_user.id, "Invalid amount. Please enter a positive number.", reply_markup=get_kb_return(message.from_user.id))
        return

    await state.update_data(amount=amount)
    data = await state.get_data()
    recipient_address = data.get('recipient_address')

    confirmation_message = f"Please confirm sending {amount} TON to the address: \n<code>{recipient_address}</code>"
    await send_message(session, message.from_user.id, confirmation_message, reply_markup=get_kb_ton_yesno(message.from_user.id))
    await state.set_state(StateSendTon.sending_confirmation)
    await message.delete()


@router.callback_query(StateSendTon.sending_confirmation, F.data == "ton_yes")
async def cmd_send_ton_confirm(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    recipient_address = data.get('recipient_address')
    amount = data.get('amount')
    user_id = callback.from_user.id

    wallet = db_get_default_wallet(session=session, user_id=user_id)
    if wallet.secret_key == 'TON':
        try:
            ton_service = TonService()
            ton_service.from_mnemonic(wallet.seed_key)

            await send_message(session, user_id, "Sending transaction...")

            result = await ton_service.send_ton(recipient_address, amount)

            if result:
                await send_message(session, user_id, f"Successfully sent {amount} TON to \n<code>{recipient_address}</code>",
                                   reply_markup=get_kb_return(callback.from_user.id))
            else:
                await send_message(session, user_id, "Transaction failed. Please try again.",
                                   reply_markup=get_kb_return(callback.from_user.id))

        except Exception as e:
            await send_message(session, user_id, f"An error occurred: ")
            logger.warning(f"An error occurred: {e}")
    else:
        await send_message(session, user_id, "Your default wallet is not a TON wallet.")

    await clear_state(state)
    await callback.answer()


@router.callback_query(StateSendTon.sending_confirmation, F.data == "ton_no")
async def cmd_send_ton_cancel(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await clear_state(state)
    await send_message(session, callback.from_user.id, "Transaction cancelled.")
    await callback.answer()

# Send TON USDT

@rate_limit(3, 'private_links')
@router.callback_query(F.data == "SendTonUSDt")
async def cmd_send_ton_usdt_start(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await clear_state(state)
    await send_message(session, callback.from_user.id, "Enter recipient's address:", reply_markup=get_kb_return(callback.from_user.id))
    await state.set_state(StateSendTonUSDT.sending_for)
    await callback.answer()


@router.message(StateSendTonUSDT.sending_for)
async def cmd_send_ton_usdt_address(message: types.Message, state: FSMContext, session: Session):
    address = message.text
    # Basic address validation
    if len(address) != 48:
        await send_message(session, message.from_user.id, "Invalid address. Please enter a valid TON address.", reply_markup=get_kb_return(message.from_user.id))
        return

    await state.update_data(recipient_address=address)
    await send_message(session, message.from_user.id, "Enter amount to send:", reply_markup=get_kb_return(message.from_user.id))
    await state.set_state(StateSendTonUSDT.sending_sum)
    await message.delete()


@router.message(StateSendTonUSDT.sending_sum)
async def cmd_send_ton_usdt_sum(message: types.Message, state: FSMContext, session: Session):
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await send_message(session, message.from_user.id, "Invalid amount. Please enter a positive number.", reply_markup=get_kb_return(message.from_user.id))
        return

    await state.update_data(amount=amount)
    data = await state.get_data()
    recipient_address = data.get('recipient_address')

    confirmation_message = f"Please confirm sending {amount} USDT to the address: \n<code>{recipient_address}</code>"
    await send_message(session, message.from_user.id, confirmation_message, reply_markup=get_kb_ton_yesno(message.from_user.id))
    await state.set_state(StateSendTonUSDT.sending_confirmation)
    await message.delete()


@router.callback_query(StateSendTonUSDT.sending_confirmation, F.data == "ton_yes")
async def cmd_send_ton_usdt_confirm(callback: types.CallbackQuery, state: FSMContext, session: Session):
    data = await state.get_data()
    recipient_address = data.get('recipient_address')
    amount = data.get('amount')
    user_id = callback.from_user.id

    wallet = db_get_default_wallet(session=session, user_id=user_id)
    if wallet.secret_key == 'TON':
        try:
            ton_service = TonService()
            ton_service.from_mnemonic(wallet.seed_key)

            await send_message(session, user_id, "Sending transaction...")

            result = await ton_service.send_usdt(recipient_address, amount)

            if result:
                await send_message(session, user_id, f"Successfully sent {amount} USDT to \n<code>{recipient_address}</code>",
                                   reply_markup=get_kb_return(callback.from_user.id))
            else:
                await send_message(session, user_id, "Transaction failed. Please try again.",
                                   reply_markup=get_kb_return(callback.from_user.id))

        except Exception as e:
            await send_message(session, user_id, f"An error occurred: ")
            logger.warning(f"An error occurred: {e}")
    else:
        await send_message(session, user_id, "Your default wallet is not a TON wallet.",
                           reply_markup=get_kb_return(callback.from_user.id))

    await clear_state(state)
    await callback.answer()


@router.callback_query(StateSendTonUSDT.sending_confirmation, F.data == "ton_no")
async def cmd_send_ton_usdt_cancel(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await clear_state(state)
    await send_message(session, callback.from_user.id, "Transaction cancelled.")
    await callback.answer()