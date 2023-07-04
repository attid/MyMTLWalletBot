from asyncio import sleep
from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from keyboards.common_keyboards import get_return_button, get_kb_return, get_kb_yesno_send_xdr
from routers.start_msg import cmd_info_message
from utils.aiogram_utils import send_message, admin_id
from utils.common_utils import get_user_id
from utils.lang_utils import my_gettext
from utils.stellar_utils import *
from utils.thothpay_utils import thoth_create_order, thoth_check_order
from utils.tron_utils import *
from aiogram.filters import Text

router = Router()


class StateInOut(StatesGroup):
    sending_usdt_address = State()
    sending_usdt_sum = State()
    sending_btc_address = State()
    sending_btc_sum_in = State()
    sending_btc_sum_out = State()


max_usdt_sum = 500
min_btc_sum = 300
max_btc_sum = 500000


@router.callback_query(Text(text=["InOut"]))
async def cmd_inout(callback: types.CallbackQuery, session: Session):
    msg = my_gettext(callback, "inout")
    buttons = [[types.InlineKeyboardButton(text='USDT TRC20',
                                           callback_data="USDT_TRC20"),
                types.InlineKeyboardButton(text='BTC lightning',
                                           callback_data="BTC"),
                ], get_return_button(callback)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard)
    await callback.answer()


############################################################################
############################################################################
############################################################################


@router.callback_query(Text(text=["USDT_TRC20"]))
async def cmd_receive_usdt(callback: types.CallbackQuery, session: Session):
    msg = my_gettext(callback, "inout_usdt")
    buttons = [[types.InlineKeyboardButton(text=my_gettext(callback, 'kb_in'),
                                           callback_data="USDT_IN"),
                types.InlineKeyboardButton(text=my_gettext(callback, 'kb_out'),
                                           callback_data="USDT_OUT"),
                ], get_return_button(callback)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard)
    await callback.answer()


############################################################################
############################################################################
############################################################################

@router.callback_query(Text(text=["USDT_IN"]))
async def cmd_usdt_in(callback: types.CallbackQuery, state: FSMContext, session: Session):
    user_tron_private_key = get_usdt_private_key(session, get_user_id(callback), create_trc_private_key)
    usdc_sum = float((await stellar_get_balances(session, 0, asset_filter='USDC'))[0].balance)

    show_max_sum = max_usdt_sum if usdc_sum > max_usdt_sum else usdc_sum

    msg = my_gettext(callback, "usdt_in", (show_max_sum, tron_get_public(user_tron_private_key)))
    buttons = [[types.InlineKeyboardButton(text=my_gettext(callback, 'kb_check'),
                                           callback_data="USDT_CHECK"),
                ], get_return_button(callback)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(Text(text=["USDT_CHECK"]))
async def cmd_usdt_check(callback: types.CallbackQuery, state: FSMContext, session: Session):
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
    if len(await stellar_get_balances(session, callback.from_user.id, asset_filter='USDC')) == 0:
        await callback.answer(text=f"You don't have a trust line to USDC, continuation is not possible",
                              show_alert=True)
        return
    user_tron_private_key = get_usdt_private_key(session, get_user_id(callback), create_trc_private_key)
    usdt_balance = await get_usdt_balance(private_key=user_tron_private_key)
    if usdt_balance < 10:
        await callback.answer(text=f"USDT account balance unchanged", show_alert=True)
        return
    usdc_sum = float((await stellar_get_balances(session, 0, asset_filter='USDC'))[0].balance)
    if usdt_balance > max_usdt_sum + 10 or usdt_balance > usdc_sum:
        await callback.answer(text=f"Amount exceeds the maximum payout limit, payment is not possible.",
                              show_alert=True)
        return
    last_usdt_transaction_sum = await get_last_usdt_transaction_sum(private_key=user_tron_private_key)
    if last_usdt_transaction_sum is None or round(usdt_balance) != round(last_usdt_transaction_sum):
        await callback.answer(
            text=f"Congratulations, it seems like your account has been credited with {round(usdt_balance)}. We are waiting for confirmations. 30 seconds",
            show_alert=True)
        return
    # all is good ?
    await callback.answer(text=f"Found {round(usdt_balance)} USDT, wait transaction",
                          show_alert=True)
    await sleep(1)
    if await get_trx_balance(private_key=user_tron_private_key) < 40:
        await send_trx_async(amount=50, private_key_to=user_tron_private_key)
    await send_usdt_async(amount=usdt_balance, private_key_to=tron_master_key, private_key_from=user_tron_private_key)
    master = stellar_get_master(session)
    xdr = stellar_sign((await stellar_pay((await stellar_get_user_account(session, 0)).account.account_id,
                                          (await stellar_get_user_account(session,
                                                                          callback.from_user.id)).account.account_id,
                                          usdc_asset, amount=round(usdt_balance) - 1)), master.secret)
    logger.info(xdr)
    await async_stellar_send(xdr)
    await cmd_info_message(session, callback, 'All works done!')


############################################################################
############################################################################
############################################################################

@router.callback_query(Text(text=["USDT_OUT"]))
async def cmd_usdt_out(callback: types.CallbackQuery, state: FSMContext, session: Session):
    usdt_master_balance = await get_usdt_balance(private_key=tron_master_key)
    show_max_sum = max_usdt_sum if usdt_master_balance > max_usdt_sum else usdt_master_balance

    msg = my_gettext(callback, "usdt_out", (show_max_sum,))
    await send_message(session, callback, msg, reply_markup=get_kb_return(callback))
    await callback.answer()
    await state.update_data(msg=msg)
    await state.set_state(StateInOut.sending_usdt_address)


async def cmd_after_send_usdt(session: Session, user_id: int, state: FSMContext):
    data = await state.get_data()
    usdt_address = data.get('usdt_address')
    usdt_sum = data.get('usdt_sum')
    await send_message(session, user_id=admin_id, msg=f'{user_id} {usdt_sum} usdt {usdt_address}', need_new_msg=True,
                       reply_markup=get_kb_return(user_id))
    await send_usdt_async(amount=usdt_sum, public_key_to=usdt_address)


@router.message(StateInOut.sending_usdt_address)
async def cmd_send_get_address(message: types.Message, state: FSMContext, session: Session):
    try:
        if len(message.text) != 34:
            raise ValueError
        trx_sum = await get_trx_balance(public_key=message.text)
        if trx_sum == 0:
            raise ValueError
        await state.update_data(usdt_address=message.text, fsm_after_send=jsonpickle.dumps(cmd_after_send_usdt))
        await state.set_state(None)
        usdc_balance = await stellar_get_balances(session, message.from_user.id, asset_filter='USDC')
        if len(usdc_balance) == 0:
            usdc_balance = 0
        else:
            usdc_balance = usdc_balance[0].balance
        await send_message(session, message,
                           my_gettext(message, 'send_sum', ('USDC', float(usdc_balance))),
                           reply_markup=get_kb_return(message))
        await state.set_state(StateInOut.sending_usdt_sum)
    except:
        data = await state.get_data()
        await send_message(session, message, f"{my_gettext(message, 'bad_key')}\n{data['msg']}")
    await message.delete()


@router.message(StateInOut.sending_usdt_sum)
async def cmd_send_get_sum(message: types.Message, state: FSMContext, session: Session):
    try:
        send_sum = my_float(message.text)
    except:
        send_sum = 0.0

    data = await state.get_data()

    if send_sum < 10 or len(await stellar_get_balances(session, message.from_user.id, asset_filter='USDC')) == 0 or \
            send_sum > float(
        (await stellar_get_balances(session, message.from_user.id, asset_filter='USDC'))[0].balance) \
            or send_sum > max_usdt_sum:
        await send_message(session, message, f"{my_gettext(message, 'bad_sum')}\n{data['msg']}")
    else:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)
        await cmd_send_usdt(session, message, state)
    await message.delete()


async def cmd_send_usdt(session: Session, message: types.Message, state: FSMContext):
    data = await state.get_data()

    send_sum = data.get("send_sum")
    send_address = (await stellar_get_user_account(session, 0)).account.account_id
    send_memo = 'For USDT'
    usdt_sum = int(send_sum) - 3
    await state.update_data(usdt_sum=usdt_sum)

    msg = my_gettext(message, 'confirm_send', (float2str(send_sum), usdc_asset.code, send_address, send_memo))
    msg += f"\n you will receive {usdt_sum} USDT for this address <b>{data.get('usdt_address')}</b>"

    xdr = await stellar_pay((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
                            send_address,
                            usdc_asset, send_sum, memo=send_memo)

    await state.update_data(xdr=xdr)

    await send_message(session, message, msg, reply_markup=get_kb_yesno_send_xdr(message))


############################################################################
############################################################################
############################################################################

@router.callback_query(Text(text=["BTC"]))
async def cmd_receive_btc(callback: types.CallbackQuery, session: Session):
    # await callback.answer('Not implemented yet', show_alert=True)
    msg = my_gettext(callback, "inout_btc")
    buttons = [[types.InlineKeyboardButton(text=my_gettext(callback, 'kb_in'),
                                           callback_data="BTC_IN"),
                types.InlineKeyboardButton(text=my_gettext(callback, 'kb_out'),
                                           callback_data="BTC_OUT"),
                ], get_return_button(callback)]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(session, callback, msg, reply_markup=keyboard)
    await callback.answer()


############################################################################
############################################################################
############################################################################

@router.callback_query(Text(text=["BTC_IN"]))
async def cmd_btc_in(callback: types.CallbackQuery, state: FSMContext, session: Session):
    await cmd_show_btc_in(session, callback.from_user.id, state)
    await callback.answer()


async def cmd_show_btc_in(session: Session, user_id: int, state: FSMContext):
    btc_uuid, btc_date = get_btc_uuid(session, user_id=user_id)
    if btc_uuid and btc_date and btc_date > datetime.now():
        buttons = [[types.InlineKeyboardButton(text=my_gettext(user_id, 'kb_check'),
                                               callback_data="BTC_CHECK"),
                    ], get_return_button(user_id)]
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        link = f'<a href="https://thothpay.com/invoice?id={btc_uuid}">{btc_uuid}</a>'
        msg = my_gettext(user_id, "btc_in_2", (link, btc_date.strftime('%d.%m.%Y %H:%M:%S')))
        await send_message(session, user_id, msg, reply_markup=keyboard)

    else:
        sats_sum = int(float((await stellar_get_balances(session, 0, asset_filter='SATSMTL'))[0].balance))
        show_max_sum = max_btc_sum if sats_sum > max_btc_sum else sats_sum
        msg = my_gettext(user_id, "btc_in", (0, show_max_sum, min_btc_sum))
        await state.set_state(StateInOut.sending_btc_sum_in)
        await state.update_data(msg=msg)
        await send_message(session, user_id, msg, reply_markup=get_kb_return(user_id))


@router.message(StateInOut.sending_btc_sum_in)
async def cmd_send_get_sum(message: types.Message, state: FSMContext, session: Session):
    try:
        send_sum = int(message.text)
    except:
        send_sum = 0
    sats_sum = float((await stellar_get_balances(session, 0, asset_filter='SATSMTL'))[0].balance)
    show_max_sum = max_btc_sum if sats_sum > max_btc_sum else sats_sum

    data = await state.get_data()

    if send_sum < min_btc_sum or len(
            await stellar_get_balances(session, message.from_user.id, asset_filter='SATSMTL')) == 0 \
            or send_sum > show_max_sum:
        await send_message(session, message, f"{my_gettext(message, 'bad_sum')}\n{data['msg']}")
    else:
        order_uuid = await thoth_create_order(user_id=message.from_user.id, amount=send_sum)
        if order_uuid:
            await state.update_data(send_sum=send_sum)
            await state.set_state(None)
            set_btc_uuid(session, user_id=message.from_user.id, btc_uuid=order_uuid)
            await cmd_show_btc_in(session, message.from_user.id, state)
    await message.delete()


@router.callback_query(Text(text=["BTC_CHECK"]))
async def cmd_btc_check(callback: types.CallbackQuery, state: FSMContext, session: Session):
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
    btc_uuid, btc_date = get_btc_uuid(session, user_id=callback.from_user.id)
    if btc_uuid and btc_date and btc_date > datetime.now():
        result, sats_sum = await thoth_check_order(btc_uuid)
        if result:
            if len(await stellar_get_balances(session, callback.from_user.id, asset_filter='SATSMTL')) == 0:
                await callback.answer(text=f"You don't have a trust line to SATSMTL, continuation is not possible",
                                      show_alert=True)
                return
            btc_balance = float((await stellar_get_balances(session, 0, asset_filter='SATSMTL'))[0].balance)
            if sats_sum > max_btc_sum or sats_sum > btc_balance:
                await callback.answer(text=f"Amount exceeds the maximum payout limit, payment is not possible.",
                                      show_alert=True)
                return
            # all is good ?
            await callback.answer(text=f"Found {round(sats_sum)} SATS, wait transaction",
                                  show_alert=True)
            await sleep(1)

            master = stellar_get_master(session)
            xdr = stellar_sign(await stellar_pay((await stellar_get_user_account(session, 0)).account.account_id,
                                                 (await stellar_get_user_account(session,
                                                                                 callback.from_user.id)).account.account_id,
                                                 satsmtl_asset, amount=round(sats_sum)), master.secret)
            logger.info(xdr)
            set_btc_uuid(session, user_id=callback.from_user.id, btc_uuid=None)
            await async_stellar_send(xdr)
            await cmd_info_message(session, callback, 'All works done!')
    await callback.answer()


############################################################################
############################################################################
############################################################################

@router.callback_query(Text(text=["BTC_OUT"]))
async def cmd_btc_out(callback: types.CallbackQuery, state: FSMContext, session:Session):
    await callback.answer('Not implemented yet', show_alert=True)
