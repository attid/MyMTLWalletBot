from asyncio import sleep
from datetime import datetime, timedelta
from typing import Union

from aiogram import Router, types
from aiogram.filters import Command, Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from fb import get_usdt_private_key
from keyboards.common_keyboards import get_return_button, get_kb_return, get_kb_yesno_send_xdr
from routers.start_msg import cmd_info_message
from utils.aiogram_utils import send_message
from utils.common_utils import get_user_id
from utils.lang_utils import my_gettext
from utils.stellar_utils import *
from utils.tron_utils import *

router = Router()


class StateInOut(StatesGroup):
    sending_usdt_address = State()
    sending_usdt_sum = State()
    sending_btc_address = State()
    sending_btc_sum = State()


max_max_usdt = 500


@router.callback_query(Text(text=["InOut"]))
async def cmd_receive(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, "inout")
    buttons = [[types.InlineKeyboardButton(text='USDT TRC20',
                                           callback_data="USDT_TRC20"),
                types.InlineKeyboardButton(text='BTC lightning',
                                           callback_data="BTC"),
                ], get_return_button(callback)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(callback, msg, reply_markup=keyboard)
    await callback.answer()


############################################################################
############################################################################
############################################################################


@router.callback_query(Text(text=["USDT_TRC20"]))
async def cmd_receive(callback: types.CallbackQuery, state: FSMContext):
    msg = my_gettext(callback, "inout_usdt")
    buttons = [[types.InlineKeyboardButton(text=my_gettext(callback, 'kb_in'),
                                           callback_data="USDT_IN"),
                types.InlineKeyboardButton(text=my_gettext(callback, 'kb_out'),
                                           callback_data="USDT_OUT"),
                ], get_return_button(callback)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(callback, msg, reply_markup=keyboard)
    await callback.answer()


############################################################################
############################################################################
############################################################################

@router.callback_query(Text(text=["USDT_IN"]))
async def cmd_receive(callback: types.CallbackQuery, state: FSMContext):
    user_tron_private_key = get_usdt_private_key(get_user_id(callback), create_trc_private_key)
    usdc_sum = float((await stellar_get_balances(0, asset_filter='USDC'))[0].balance)

    show_max_sum = max_max_usdt if usdc_sum > max_max_usdt else usdc_sum

    msg = my_gettext(callback, "usdt_in", (show_max_sum, tron_get_public(user_tron_private_key)))
    buttons = [[types.InlineKeyboardButton(text=my_gettext(callback, 'kb_check'),
                                           callback_data="USDT_CHECK"),
                ], get_return_button(callback)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(callback, msg, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(Text(text=["USDT_CHECK"]))
async def cmd_receive(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    check_time = data.get("check_time")
    if check_time and datetime.now() < datetime.strptime(check_time, '%d.%m.%Y %H:%M:%S') + timedelta(seconds=10):
        remaining_seconds = int((datetime.strptime(check_time, '%d.%m.%Y %H:%M:%S') + timedelta(
            seconds=10) - datetime.now()).total_seconds())
        await callback.answer(text=f"Too frequent requests, please try again in {remaining_seconds} seconds.",
                              show_alert=True)
        return
    await state.update_data(check_time=datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
    # rest of the function logic
    if len(await stellar_get_balances(callback.from_user.id, asset_filter='USDC')) == 0:
        await callback.answer(text=f"You don't have a trust line to USDC, continuation is not possible",
                              show_alert=True)
        return
    user_tron_private_key = get_usdt_private_key(get_user_id(callback), create_trc_private_key)
    usdt_balance = await get_usdt_balance(private_key=user_tron_private_key)
    if usdt_balance < 10:
        await callback.answer(text=f"USDT account balance unchanged", show_alert=True)
        return
    usdc_sum = float((await stellar_get_balances(0, asset_filter='USDC'))[0].balance)
    if usdt_balance > max_max_usdt or usdt_balance > usdc_sum:
        await callback.answer(text=f"Amount exceeds the maximum payout limit, payment is not possible.",
                              show_alert=True)
        return
    last_usdt_transaction_sum = await get_last_usdt_transaction_sum(private_key=user_tron_private_key)
    if last_usdt_transaction_sum is None or usdt_balance != last_usdt_transaction_sum:
        await callback.answer(
            text=f"Not found transaction for the amount of {usdt_balance}, maybe there are not enough confirmations",
            show_alert=True)
        return
    # all is good ?
    await callback.answer(text=f"Found {round(usdt_balance)} USDT, create transaction",
                          show_alert=True)
    await sleep(1)
    if await get_trx_balance(private_key=user_tron_private_key) < 40:
        await send_trx_async(amount=50, private_key_to=user_tron_private_key)
    await send_usdt_async(amount=usdt_balance, private_key_to=tron_master_key, private_key_from=user_tron_private_key)
    master = stellar_get_master()
    xdr = stellar_sign((await stellar_pay((await stellar_get_user_account(0)).account.account_id,
                                          (await stellar_get_user_account(callback.from_user.id)).account.account_id,
                                          usdc_asset, amount=round(usdt_balance) - 1)), master.secret)
    logger.info(xdr)
    await async_stellar_send(xdr)
    await cmd_info_message(callback, 'All works done!', state)


############################################################################
############################################################################
############################################################################

@router.callback_query(Text(text=["USDT_OUT"]))
async def cmd_receive(callback: types.CallbackQuery, state: FSMContext):
    usdt_master_balance = await get_usdt_balance(private_key=tron_master_key)
    show_max_sum = max_max_usdt if usdt_master_balance > max_max_usdt else usdt_master_balance

    msg = my_gettext(callback, "usdt_out", (show_max_sum,))
    await send_message(callback, msg, reply_markup=get_kb_return(callback))
    await callback.answer()
    await state.update_data(msg=msg)
    await state.set_state(StateInOut.sending_usdt_address)


@router.message(StateInOut.sending_usdt_address)
async def cmd_send_get_address(message: types.Message, state: FSMContext):
    try:
        if len(message.text) != 34:
            raise ValueError
        trx_sum = await get_trx_balance(public_key=message.text)
        if trx_sum == 0:
            raise ValueError
        await state.update_data(usdt_address=message.text)
        await state.set_state(None)
        usdc_balance = await stellar_get_balances(message.from_user.id, asset_filter='USDC')
        if len(usdc_balance) == 0:
            usdc_balance = 0
        else:
            usdc_balance = usdc_balance[0].balance
        await send_message(message,
                           my_gettext(message, 'send_sum', ('USDC', float(usdc_balance))),
                           reply_markup=get_kb_return(message))
        await state.set_state(StateInOut.sending_usdt_sum)
    except:
        data = await state.get_data()
        await send_message(message, f"{my_gettext(message, 'bad_key')}\n{data['msg']}")
    await message.delete()


@router.message(StateInOut.sending_usdt_sum)
async def cmd_send_get_sum(message: types.Message, state: FSMContext):
    try:
        send_sum = my_float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()

    if send_sum < 10 or len(await stellar_get_balances(message.from_user.id, asset_filter='USDC')) == 0 or \
            send_sum > float((await stellar_get_balances(message.from_user.id, asset_filter='USDC'))[0].balance) \
            or send_sum > max_max_usdt:
        await send_message(message, f"{my_gettext(message, 'bad_sum')}\n{data['msg']}")
    else:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)
        await cmd_send_usdt(message, state)
    await message.delete()


async def cmd_send_usdt(message: types.Message, state: FSMContext):
    data = await state.get_data()

    send_sum = data.get("send_sum")
    send_address = (await stellar_get_user_account(0)).account.account_id
    send_memo = 'For USDT'
    usdt_sum = int(send_sum) - 3
    await state.update_data(usdt_sum=usdt_sum)

    msg = my_gettext(message, 'confirm_send', (float2str(send_sum), usdc_asset.code, send_address, send_memo))
    msg += f"\n you will receive {usdt_sum} USDT for this address <b>{data.get('usdt_address')}</b>"


    xdr = await stellar_pay((await stellar_get_user_account(message.from_user.id)).account.account_id,
                            send_address,
                            usdc_asset, send_sum, memo=send_memo)

    await state.update_data(xdr=xdr)

    await send_message(message, msg, reply_markup=get_kb_yesno_send_xdr(message))


############################################################################
############################################################################
############################################################################

@router.callback_query(Text(text=["BTC"]))
async def cmd_receive(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer('Not implemented yet', show_alert=True)
