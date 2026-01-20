from typing import Union

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


from keyboards.common_keyboards import get_kb_return
from middleware.throttling import rate_limit
from infrastructure.utils.telegram_utils import send_message, clear_state
from infrastructure.utils.common_utils import get_user_id
from infrastructure.services.app_context import AppContext
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
async def cmd_send_ton_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    await clear_state(state)
    await send_message(session, callback.from_user.id, "Enter recipient's address:", reply_markup=get_kb_return(callback.from_user.id, app_context=app_context), app_context=app_context)
    await state.set_state(StateSendTon.sending_for)
    await callback.answer()


@router.message(StateSendTon.sending_for)
async def cmd_send_ton_address(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None:
        return
    address = message.text
    # Basic address validation
    if len(address) != 48:
        await send_message(session, message.from_user.id, "Invalid address. Please enter a valid TON address.", reply_markup=get_kb_return(message.from_user.id, app_context=app_context), app_context=app_context)
        return

    await state.update_data(recipient_address=address)
    await send_message(session, message.from_user.id, "Enter amount to send:", reply_markup=get_kb_return(message.from_user.id, app_context=app_context), app_context=app_context)
    await state.set_state(StateSendTon.sending_sum)
    await message.delete()


@router.message(StateSendTon.sending_sum)
async def cmd_send_ton_sum(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None:
        return
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await send_message(session, message.from_user.id, "Invalid amount. Please enter a positive number.", reply_markup=get_kb_return(message.from_user.id, app_context=app_context), app_context=app_context)
        return

    await state.update_data(amount=amount)
    data = await state.get_data()
    recipient_address = data.get('recipient_address')

    confirmation_message = f"Please confirm sending {amount} TON to the address: \n<code>{recipient_address}</code>"
    await send_message(session, message.from_user.id, confirmation_message, reply_markup=get_kb_ton_yesno(message.from_user.id), app_context=app_context)
    await state.set_state(StateSendTon.sending_confirmation)
    await message.delete()


@router.callback_query(StateSendTon.sending_confirmation, F.data == "ton_yes")
async def cmd_send_ton_confirm(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    data = await state.get_data()
    recipient_address = data.get('recipient_address')
    amount = data.get('amount')
    user_id = callback.from_user.id

    from infrastructure.services.wallet_secret_service import SqlAlchemyWalletSecretService
    if app_context.use_case_factory:
        secret_service = app_context.use_case_factory.create_wallet_secret_service(session)
    else:
        secret_service = SqlAlchemyWalletSecretService(session)
    
    if await secret_service.is_ton_wallet(user_id):
        try:
            mnemonic = await secret_service.get_ton_mnemonic(user_id)
            if mnemonic is None or recipient_address is None or amount is None:
                 return
            ton_service = app_context.ton_service or TonService()
            ton_service.from_mnemonic(mnemonic)

            await send_message(session, user_id, "Sending transaction...", app_context=app_context)

            result = await ton_service.send_ton(recipient_address, amount)

            if result:
                await send_message(session, user_id, f"Successfully sent {amount} TON to \n<code>{recipient_address}</code>",
                                   reply_markup=get_kb_return(callback.from_user.id, app_context=app_context), app_context=app_context)
            else:
                await send_message(session, user_id, "Transaction failed. Please try again.",
                                   reply_markup=get_kb_return(callback.from_user.id, app_context=app_context), app_context=app_context)

        except Exception as e:
            await send_message(session, user_id, f"An error occurred: ", app_context=app_context)
            logger.warning(f"An error occurred: {e}")
    else:
        await send_message(session, user_id, "Your default wallet is not a TON wallet.", app_context=app_context)

    await clear_state(state)
    await state.set_state(None)
    await callback.answer()


@router.callback_query(StateSendTon.sending_confirmation, F.data == "ton_no")
async def cmd_send_ton_cancel(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    await clear_state(state)
    await state.set_state(None)
    await send_message(session, callback.from_user.id, "Transaction cancelled.", app_context=app_context)
    await callback.answer()

# Send TON USDT

@rate_limit(3, 'private_links')
@router.callback_query(F.data == "SendTonUSDt")
async def cmd_send_ton_usdt_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    await clear_state(state)
    await send_message(session, callback.from_user.id, "Enter recipient's address:", reply_markup=get_kb_return(callback.from_user.id, app_context=app_context), app_context=app_context)
    await state.set_state(StateSendTonUSDT.sending_for)
    await callback.answer()


@router.message(StateSendTonUSDT.sending_for)
async def cmd_send_ton_usdt_address(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None:
        return
    address = message.text
    # Basic address validation
    if len(address) != 48:
        await send_message(session, message.from_user.id, "Invalid address. Please enter a valid TON address.", reply_markup=get_kb_return(message.from_user.id, app_context=app_context), app_context=app_context)
        return

    await state.update_data(recipient_address=address)
    await send_message(session, message.from_user.id, "Enter amount to send:", reply_markup=get_kb_return(message.from_user.id, app_context=app_context), app_context=app_context)
    await state.set_state(StateSendTonUSDT.sending_sum)
    await message.delete()


@router.message(StateSendTonUSDT.sending_sum)
async def cmd_send_ton_usdt_sum(message: types.Message, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if message.from_user is None or message.text is None:
        return
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await send_message(session, message.from_user.id, "Invalid amount. Please enter a positive number.", reply_markup=get_kb_return(message.from_user.id, app_context=app_context), app_context=app_context)
        return

    await state.update_data(amount=amount)
    data = await state.get_data()
    recipient_address = data.get('recipient_address')

    confirmation_message = f"Please confirm sending {amount} USDT to the address: \n<code>{recipient_address}</code>"
    await send_message(session, message.from_user.id, confirmation_message, reply_markup=get_kb_ton_yesno(message.from_user.id), app_context=app_context)
    await state.set_state(StateSendTonUSDT.sending_confirmation)
    await message.delete()


@router.callback_query(StateSendTonUSDT.sending_confirmation, F.data == "ton_yes")
async def cmd_send_ton_usdt_confirm(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    if callback.from_user is None:
        return
    data = await state.get_data()
    recipient_address = data.get('recipient_address')
    amount = data.get('amount')
    user_id = callback.from_user.id

    from infrastructure.services.wallet_secret_service import SqlAlchemyWalletSecretService
    if app_context.use_case_factory:
        secret_service = app_context.use_case_factory.create_wallet_secret_service(session)
    else:
        secret_service = SqlAlchemyWalletSecretService(session)
    
    if await secret_service.is_ton_wallet(user_id):
        try:
            mnemonic = await secret_service.get_ton_mnemonic(user_id)
            if mnemonic is None or recipient_address is None or amount is None:
                 return
            ton_service = app_context.ton_service or TonService()
            ton_service.from_mnemonic(mnemonic)

            await send_message(session, user_id, "Sending transaction...", app_context=app_context)

            result = await ton_service.send_usdt(recipient_address, amount)

            if result:
                await send_message(session, user_id, f"Successfully sent {amount} USDT to \n<code>{recipient_address}</code>",
                                   reply_markup=get_kb_return(callback.from_user.id, app_context=app_context), app_context=app_context)
            else:
                await send_message(session, user_id, "Transaction failed. Please try again.",
                                   reply_markup=get_kb_return(callback.from_user.id, app_context=app_context), app_context=app_context)

        except Exception as e:
            await send_message(session, user_id, f"An error occurred: ", app_context=app_context)
            logger.warning(f"An error occurred: {e}")
    else:
        await send_message(session, user_id, "Your default wallet is not a TON wallet.",
                           reply_markup=get_kb_return(callback.from_user.id, app_context=app_context), app_context=app_context)

    await clear_state(state)
    await state.set_state(None)
    await callback.answer()


@router.callback_query(StateSendTonUSDT.sending_confirmation, F.data == "ton_no")
async def cmd_send_ton_usdt_cancel(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession, app_context: AppContext):
    await clear_state(state)
    await state.set_state(None)
    await send_message(session, callback.from_user.id, "Transaction cancelled.", app_context=app_context)
    await callback.answer()
