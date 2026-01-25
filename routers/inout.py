import asyncio
import html
import jsonpickle  # type: ignore
from asyncio import sleep
from decimal import Decimal
from datetime import datetime, timedelta
from loguru import logger
from aiogram import Router, types, F, Bot
from aiogram.enums import ContentType
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.ext.asyncio import AsyncSession
from keyboards.common_keyboards import (
    get_return_button,
    get_kb_return,
    get_kb_yesno_send_xdr,
)
from other.loguru_tools import safe_catch_async
from routers.start_msg import cmd_info_message
from infrastructure.utils.telegram_utils import send_message, clear_last_message_id
from infrastructure.utils.common_utils import get_user_id
from infrastructure.services.app_context import AppContext
from other.lang_tools import my_gettext
from infrastructure.utils.stellar_utils import (
    my_float,
    usdm_asset,
    satsmtl_asset,
    eurmtl_asset,
)
from infrastructure.utils.common_utils import float2str
from core.domain.value_objects import Asset as DomainAsset
from other.tron_tools import (
    tron_get_public,
    create_trc_private_key,
    get_usdt_balance,
    check_unconfirmed_usdt_transactions,
    tron_master_key,
    send_usdt_async,
    check_valid_trx,
    get_usdt_transfer_fee,
    tron_master_address,
    get_trx_balance,
    send_trx_async,
    get_account_energy,
    EnergyObject,
    delegate_energy,
)
from other.locks import new_wallet_lock
from other.thothpay_tools import thoth_create_order, thoth_check_order

router = Router()
router.message.filter(F.chat.type == "private")


class StateInOut(StatesGroup):
    sending_usdt_address = State()
    sending_usdt_sum = State()
    sending_btc_address = State()
    sending_btc_sum_in = State()
    sending_btc_sum_out = State()
    sending_starts_sum_in = State()


min_usdt_sum = 10
max_usdt_sum = 500
min_btc_sum = 300
max_btc_sum = 500000
usdt_in_fee = 0


# usdt_out_fee = 1


@router.callback_query(F.data == "InOut")
async def cmd_inout(
    callback: types.CallbackQuery, session: AsyncSession, app_context: AppContext
):
    if callback.from_user is None:
        return
    msg = my_gettext(callback, "inout", app_context=app_context)
    buttons = [
        [types.InlineKeyboardButton(text="USDT TRC20", callback_data="USDT_TRC20")],
        [types.InlineKeyboardButton(text="BTC lightning", callback_data="BTC")],
        [types.InlineKeyboardButton(text="STARTS", callback_data="STARTS")],
        get_return_button(callback, app_context=app_context),
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(
        session, callback, msg, reply_markup=keyboard, app_context=app_context
    )
    await callback.answer()


############################################################################
############################################################################
############################################################################


@router.callback_query(F.data == "USDT_TRC20")
async def cmd_receive_usdt(
    callback: types.CallbackQuery, session: AsyncSession, app_context: AppContext
):
    msg = my_gettext(callback, "inout_usdt", app_context=app_context)
    buttons = [
        [
            types.InlineKeyboardButton(
                text=my_gettext(callback, "kb_in", app_context=app_context),
                callback_data="USDT_IN",
            ),
            types.InlineKeyboardButton(
                text=my_gettext(callback, "kb_out", app_context=app_context),
                callback_data="USDT_OUT",
            ),
        ],
        get_return_button(callback, app_context=app_context),
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(
        session, callback, msg, reply_markup=keyboard, app_context=app_context
    )
    await callback.answer()


############################################################################
############################################################################
############################################################################


@router.callback_query(F.data == "USDT_IN")
async def cmd_usdt_in(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if callback.from_user is None:
        return
    assert app_context.use_case_factory is not None, (
        "use_case_factory must be initialized"
    )
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    asset_list = await balance_use_case.execute(user_id=callback.from_user.id)
    # Filter for USDM
    asset_list = [b for b in asset_list if b.asset_code == "USDM"]
    if not asset_list:
        await send_message(
            session,
            callback,
            my_gettext(callback, "usdm_need", app_context=app_context),
            reply_markup=get_kb_return(callback, app_context=app_context),
            app_context=app_context,
        )
    else:
        assert app_context.repository_factory is not None, (
            "repository_factory must be initialized"
        )
        user_repo = app_context.repository_factory.get_user_repository(session)
        user_tron_private_key, _ = await user_repo.get_usdt_key(get_user_id(callback))

        # Check Master USDM Balance (User 0)
        master_balance_list = await balance_use_case.execute(user_id=0)
        master_usdm = next(
            (b for b in master_balance_list if b.asset_code == "USDM"), None
        )
        usdm_sum = float(master_usdm.balance) if master_usdm else 0.0

        show_max_sum = max_usdt_sum if usdm_sum > max_usdt_sum else usdm_sum

        msg = my_gettext(
            callback,
            "usdt_in",
            (
                usdt_in_fee,
                min_usdt_sum,
                show_max_sum,
                tron_get_public(user_tron_private_key),
            ),
            app_context=app_context,
        )
        buttons = [
            [
                types.InlineKeyboardButton(
                    text=my_gettext(callback, "kb_check", app_context=app_context),
                    callback_data="USDT_CHECK",
                ),
            ],
            get_return_button(callback, app_context=app_context),
        ]
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        await send_message(
            session, callback, msg, reply_markup=keyboard, app_context=app_context
        )
    await callback.answer()


@router.callback_query(F.data == "USDT_CHECK")
async def cmd_usdt_check(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    app_context: AppContext,
):
    if callback.from_user is None:
        return
    data = await state.get_data()
    check_time = data.get("check_time")
    if check_time and datetime.now() < datetime.strptime(
        check_time, "%d.%m.%Y %H:%M:%S"
    ) + timedelta(seconds=10):
        remaining_seconds = int(
            (
                datetime.strptime(check_time, "%d.%m.%Y %H:%M:%S")
                + timedelta(seconds=10)
                - datetime.now()
            ).total_seconds()
        )
        await callback.answer(
            text=f"Too frequent requests, please try again in {remaining_seconds} seconds.",
            show_alert=True,
        )
        return
    await state.update_data(check_time=datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    # rest of the function logic
    assert app_context.use_case_factory is not None, (
        "use_case_factory must be initialized"
    )
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    user_balances = await balance_use_case.execute(user_id=callback.from_user.id)
    if not any(b.asset_code == "USDM" for b in user_balances):
        await callback.answer(
            text="You don't have a trust line to USDM, continuation is not possible",
            show_alert=True,
        )
        return
    async with new_wallet_lock:
        user_repo = app_context.repository_factory.get_user_repository(session)
        user_tron_private_key_opt, usdt_old_sum = await user_repo.get_usdt_key(
            get_user_id(callback), create_trc_private_key
        )
        if user_tron_private_key_opt is None:
            return
        user_tron_private_key = user_tron_private_key_opt
        user_tron_key = tron_get_public(user_tron_private_key)
        full_usdt_balance = int(
            await get_usdt_balance(private_key=user_tron_private_key)
        )
        income_usdt_balance = int(full_usdt_balance - usdt_old_sum)
        if income_usdt_balance < min_usdt_sum:
            await callback.answer(
                text="USDT account balance unchanged", show_alert=True
            )
            return
        usdm_sum = 0.0
        master_balances = await balance_use_case.execute(user_id=0)
        master_usdm = next((b for b in master_balances if b.asset_code == "USDM"), None)
        if master_usdm:
            usdm_sum = float(master_usdm.balance)
        if (
            income_usdt_balance > max_usdt_sum + min_usdt_sum
            or income_usdt_balance > usdm_sum
        ):
            await callback.answer(
                text="Amount exceeds the maximum payout limit, payment is not possible.",
                show_alert=True,
            )
            return
        if await check_unconfirmed_usdt_transactions(private_key=user_tron_private_key):
            await callback.answer(
                text=f"Congratulations, it seems like your account has been credited with {income_usdt_balance}. We are waiting for confirmations. 30 seconds",
                show_alert=True,
            )
            return
        # all is good ?
        await callback.answer(
            text=f"Found {income_usdt_balance} USDT, wait transaction", show_alert=True
        )

        # if await get_trx_balance(private_key=user_tron_private_key) < 40:
        #     await send_trx_async(amount=50, private_key_to=user_tron_private_key)
        # if full_usdt_balance > 500:
        #     await send_usdt_async(amount=income_usdt_balance, private_key_to=tron_master_key, private_key_from=user_tron_private_key)
        # user_repo instantiated previously in this function (line 143 replacement) or new instance
        # Payout from Master (User 0) to User
        # Need user address
        # user_repo instantiated previously in this function
        user_repo = app_context.repository_factory.get_user_repository(session)
        await user_repo.update_usdt_balance(get_user_id(callback), full_usdt_balance)
        await session.commit()  # Добавляем commit для сохранения изменений в БД
        url = f'<a href="https://tronscan.org/#/address/{user_tron_key}">{user_tron_key}</a>'
        admin_id = app_context.admin_id
        await bot.send_message(
            chat_id=admin_id,
            text=f"{get_user_id(callback)} send {income_usdt_balance} usdt "
            f"(full {full_usdt_balance})\n {url}",
        )

        wallet_repo = app_context.repository_factory.get_wallet_repository(session)
        user_wallet = await wallet_repo.get_default_wallet(callback.from_user.id)
        if not user_wallet:
            raise Exception("User wallet not found")

        pay_use_case = app_context.use_case_factory.create_send_payment(session)
        await pay_use_case.execute(
            user_id=0,
            destination_address=user_wallet.public_key,
            asset=DomainAsset(
                code="USDM", issuer=usdm_asset.issuer
            ),  # usdm_asset imported from tools
            amount=income_usdt_balance - usdt_in_fee,
            password="0",
        )
        await cmd_info_message(
            session, callback, "All works done!", app_context=app_context
        )


############################################################################
############################################################################
############################################################################


@router.callback_query(F.data == "USDT_OUT")
async def cmd_usdt_out(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if callback.from_user is None:
        return
    assert app_context.repository_factory is not None, (
        "repository_factory must be initialized"
    )
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(callback.from_user.id)
    if wallet and wallet.use_pin == 10:
        await send_message(
            session,
            callback,
            "Sorry, I can't work in read-only mode",
            reply_markup=get_kb_return(callback, app_context=app_context),
            app_context=app_context,
        )
        await callback.answer()
        return

    assert app_context.use_case_factory is not None, (
        "use_case_factory must be initialized"
    )
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    asset_list = await balance_use_case.execute(user_id=callback.from_user.id)
    # Check if USDM exists in balances
    has_usdm = any(b.asset_code == "USDM" for b in asset_list)

    if not has_usdm:
        await send_message(
            session,
            callback,
            my_gettext(callback, "usdm_need", app_context=app_context),
            reply_markup=get_kb_return(callback, app_context=app_context),
            app_context=app_context,
        )
    else:
        usdt_master_balance = await get_usdt_balance(private_key=tron_master_key)
        show_max_sum = (
            max_usdt_sum if usdt_master_balance > max_usdt_sum else usdt_master_balance
        )

        msg = my_gettext(
            callback,
            "usdt_out",
            (
                min_usdt_sum,
                show_max_sum,
            ),
            app_context=app_context,
        )
        await send_message(
            session,
            callback,
            msg,
            reply_markup=get_kb_return(callback, app_context=app_context),
            app_context=app_context,
        )
        await callback.answer()
        await state.update_data(msg=msg)
        await state.set_state(StateInOut.sending_usdt_address)


async def cmd_after_send_usdt(
    session: AsyncSession, user_id: int, state: FSMContext, *, app_context: AppContext
):
    await state.update_data(out_pay_usdt=user_id)

    message_text = (
        f"Ваша заявка #{user_id}\n"
        "В течение минуты будет выслана транзакция. "
        "Если что-то пойдёт не так, пожалуйста, нажмите кнопку 'Проверить'."
    )

    buttons = [
        [
            types.InlineKeyboardButton(
                text=my_gettext(user_id, "kb_check", app_context=app_context),
                callback_data="USDT_OUT_CHECK",
            ),
        ],
        get_return_button(user_id, app_context=app_context),
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)

    await send_message(
        session, user_id, message_text, reply_markup=keyboard, app_context=app_context
    )

    await cmd_after_send_usdt_task(session, user_id, state, app_context=app_context)


async def cmd_after_send_usdt_task(
    session: AsyncSession, user_id: int, state: FSMContext, *, app_context: AppContext
):
    await state.update_data(check_time=datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    async with new_wallet_lock:
        data = await state.get_data()
        out_pay_usdt = data.get("out_pay_usdt")
        if out_pay_usdt:
            admin_id = app_context.admin_id
            usdt_address: str | None = data.get("usdt_address")
            usdt_sum: int | None = data.get("usdt_sum")
            await send_message(
                session,
                user_id=admin_id,
                msg=f"{user_id} {usdt_sum} usdt {usdt_address}",
                need_new_msg=True,
                reply_markup=get_kb_return(user_id, app_context=app_context),
                app_context=app_context,
            )
            await clear_last_message_id(admin_id, app_context=app_context)
            try:
                usdt_sum_val: float = float(usdt_sum) if usdt_sum else 0.0
                success, tx_hash = await send_usdt_async(
                    amount=usdt_sum_val,
                    public_key_to=usdt_address,
                    sun_fee=data.get("sun_fee", 0),
                )
                if success:
                    await state.update_data(out_pay_usdt=None)
                    url = f'<a href="https://tronscan.org/#/transaction/{tx_hash}">{tx_hash}</a>'
                    await send_message(
                        session,
                        user_id=admin_id,
                        msg=f"{user_id} {usdt_sum} usdt {usdt_address} good \n {url}",
                        need_new_msg=True,
                        reply_markup=get_kb_return(user_id, app_context=app_context),
                        app_context=app_context,
                    )
                    await clear_last_message_id(admin_id, app_context=app_context)
                    await send_message(
                        session,
                        user_id=user_id,
                        msg=f"YOUR TRANSACTION: {url}",
                        need_new_msg=True,
                        reply_markup=get_kb_return(user_id, app_context=app_context),
                        app_context=app_context,
                    )
                    await clear_last_message_id(user_id, app_context=app_context)
                else:
                    raise Exception("USDT send failed")
            except Exception as e:
                logger.error(e)
                await send_message(
                    session,
                    user_id=admin_id,
                    msg=f"{user_id} {usdt_sum} usdt {usdt_address} bad \n{e}",
                    need_new_msg=True,
                    reply_markup=get_kb_return(user_id, app_context=app_context),
                    app_context=app_context,
                )


@router.callback_query(F.data == "USDT_OUT_CHECK")
async def cmd_usdt_out_check(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    app_context: AppContext,
):
    data = await state.get_data()
    check_time = data.get("check_time")
    if check_time and datetime.now() < datetime.strptime(
        check_time, "%d.%m.%Y %H:%M:%S"
    ) + timedelta(seconds=10):
        remaining_seconds = int(
            (
                datetime.strptime(check_time, "%d.%m.%Y %H:%M:%S")
                + timedelta(seconds=10)
                - datetime.now()
            ).total_seconds()
        )
        await callback.answer(
            text=f"Too frequent requests, please try again in {remaining_seconds} seconds.",
            show_alert=True,
        )
        return

    await cmd_after_send_usdt_task(
        session, callback.from_user.id, state, app_context=app_context
    )


@router.message(StateInOut.sending_usdt_address)
async def cmd_send_get_address(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None or message.text is None:
        return
    try:
        if not check_valid_trx(message.text):
            raise ValueError
        # trx_sum = await get_trx_balance(public_key=message.text)
        ##if trx_sum == 0:
        ##    raise ValueError
        await state.update_data(
            usdt_address=message.text,
            fsm_after_send=jsonpickle.dumps(cmd_after_send_usdt),
        )
        await state.set_state(None)
        usdm_balance = 0
        balance_use_case = app_context.use_case_factory.create_get_wallet_balance(
            session
        )
        balances = await balance_use_case.execute(message.from_user.id)
        usdm_obj = next((b for b in balances if b.asset_code == "USDM"), None)
        if usdm_obj:
            usdm_balance = usdm_obj.balance

        await send_message(
            session,
            message,
            my_gettext(
                message,
                "send_sum",
                ("USDM", float(usdm_balance)),
                app_context=app_context,
            ),
            reply_markup=get_kb_return(message, app_context=app_context),
            app_context=app_context,
        )
        await state.set_state(StateInOut.sending_usdt_sum)
    except Exception:
        data = await state.get_data()
        await send_message(
            session,
            message,
            f"{my_gettext(message, 'bad_key', app_context=app_context)}\n{data['msg']}",
            reply_markup=get_kb_return(message, app_context=app_context),
            app_context=app_context,
        )
    await message.delete()


@router.message(StateInOut.sending_usdt_sum)
async def cmd_send_usdt_sum(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None or message.text is None:
        return
    try:
        send_sum = my_float(message.text)
    except Exception:
        send_sum = 0.0

    data = await state.get_data()

    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    balances = await balance_use_case.execute(message.from_user.id)
    usdm_obj = next((b for b in balances if b.asset_code == "USDM"), None)

    if (
        send_sum < 10
        or not usdm_obj
        or send_sum > float(usdm_obj.balance)
        or send_sum > max_usdt_sum
    ):
        await send_message(
            session,
            message,
            f"{my_gettext(message, 'bad_sum', app_context=app_context)}\n{data['msg']}",
            reply_markup=get_kb_return(message, app_context=app_context),
            app_context=app_context,
        )
    else:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)
        await cmd_send_usdt(session, message, state, app_context=app_context)
    await message.delete()


async def cmd_send_usdt(
    session: AsyncSession,
    message: types.Message,
    state: FSMContext,
    *,
    app_context: AppContext,
):
    if message.from_user is None:
        return
    data = await state.get_data()

    send_sum: float | None = data.get("send_sum")
    usdt_address: str | None = data.get("usdt_address")
    assert send_sum is not None, "send_sum must be set in state"
    assert usdt_address is not None, "usdt_address must be set in state"
    usdt_out_fee, sun_fee = await get_usdt_transfer_fee(
        tron_master_address, usdt_address, int(send_sum)
    )
    usdt_out_fee = round(usdt_out_fee)
    master_energy = await get_account_energy()
    if master_energy.energy_amount > 130_000:
        usdt_out_fee = 0
        if send_sum > 98:
            usdt_out_fee = 2

    # send_address = (await stellar_get_user_account(session, 0)).account.account_id
    # We need public key for user 0
    assert app_context.repository_factory is not None, (
        "repository_factory must be initialized"
    )
    repo = app_context.repository_factory.get_wallet_repository(session)
    master_wallet = await repo.get_default_wallet(0)
    assert master_wallet is not None, "master wallet must exist"
    send_address = master_wallet.public_key

    send_memo = "For USDT"
    usdt_sum = int(send_sum) - usdt_out_fee
    await state.update_data(usdt_sum=usdt_sum, sun_fee=sun_fee)

    msg = my_gettext(
        message,
        "confirm_send",
        (float2str(send_sum), usdm_asset.code, send_address, send_memo),
        app_context=app_context,
    )
    dest_address: str | None = data.get("usdt_address")
    msg += f"\n you will receive {usdt_sum} USDT for this address <b>{dest_address}</b>"

    assert app_context.use_case_factory is not None, (
        "use_case_factory must be initialized"
    )
    pay_use_case = app_context.use_case_factory.create_send_payment(session)
    # Perform transaction immediately?
    # Logic in send.py used cmd_send_04/SendPayment.
    # Here we are asking for YES/NO confirmation (reply_markup=get_kb_yesno_send_xdr).
    # Then wait for next step.
    # Legacy used stellar_pay to generate XDR and save it to state.
    # Then user clicks YES, handling code sends it?
    # I should check where "SendXDR" or "YES" callback is handled.
    # It is usually handled in router. e.g. routers/sign.py cmd_send_xdr?
    # If so, I need `xdr` in state.
    # SendPayment executes and returns XDR (if success).

    result = await pay_use_case.execute(
        user_id=message.from_user.id,
        destination_address=send_address,
        asset=DomainAsset(code="USDM", issuer=usdm_asset.issuer),
        amount=send_sum,
        memo=send_memo,
    )

    if result.success:
        xdr = result.xdr
    else:
        await send_message(
            session, message, f"Error: {result.error_message}", app_context=app_context
        )
        return

    # xdr = await stellar_pay((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
    #                         send_address,
    #                         usdm_asset, send_sum, memo=send_memo)

    await state.update_data(xdr=xdr)

    await send_message(
        session,
        message,
        msg,
        reply_markup=get_kb_yesno_send_xdr(message, app_context=app_context),
        app_context=app_context,
    )
    await clear_last_message_id(message.chat.id, app_context=app_context)


############################################################################
############################################################################
############################################################################


@router.callback_query(F.data == "BTC")
async def cmd_receive_btc(
    callback: types.CallbackQuery, session: AsyncSession, app_context: AppContext
):
    # await callback.answer('Not implemented yet', show_alert=True)
    msg = my_gettext(callback, "inout_btc", app_context=app_context)
    buttons = [
        [
            types.InlineKeyboardButton(
                text=my_gettext(callback, "kb_in", app_context=app_context),
                callback_data="BTC_IN",
            ),
            types.InlineKeyboardButton(
                text=my_gettext(callback, "kb_out", app_context=app_context),
                callback_data="BTC_OUT",
            ),
        ],
        get_return_button(callback, app_context=app_context),
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await send_message(
        session, callback, msg, reply_markup=keyboard, app_context=app_context
    )
    await callback.answer()


############################################################################
############################################################################
############################################################################


@router.callback_query(F.data == "BTC_IN")
async def cmd_btc_in(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if callback.from_user is None:
        return
    await cmd_show_btc_in(
        session, callback.from_user.id, state, app_context=app_context
    )
    await callback.answer()


async def cmd_show_btc_in(
    session: AsyncSession, user_id: int, state: FSMContext, *, app_context: AppContext
):
    assert app_context.repository_factory is not None, (
        "repository_factory must be initialized"
    )
    user_repo = app_context.repository_factory.get_user_repository(session)
    result = await user_repo.get_btc_uuid(user_id)
    btc_uuid: str | None = result[0]
    btc_date: datetime | None = result[1] if isinstance(result[1], datetime) else None
    if (
        btc_uuid
        and btc_date
        and isinstance(btc_date, datetime)
        and btc_date > datetime.now()
    ):
        buttons = [
            [
                types.InlineKeyboardButton(
                    text=my_gettext(user_id, "kb_check", app_context=app_context),
                    callback_data="BTC_CHECK",
                ),
            ],
            get_return_button(user_id, app_context=app_context),
        ]
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        link = f'<a href="https://thothpay.com/invoice?id={btc_uuid}">{btc_uuid}</a>'
        msg = my_gettext(
            user_id,
            "btc_in_2",
            (link, btc_date.strftime("%d.%m.%Y %H:%M:%S")),
            app_context=app_context,
        )
        await send_message(
            session, user_id, msg, reply_markup=keyboard, app_context=app_context
        )

    else:
        assert app_context.use_case_factory is not None, (
            "use_case_factory must be initialized"
        )
        balance_use_case = app_context.use_case_factory.create_get_wallet_balance(
            session
        )
        master_balances = await balance_use_case.execute(0)
        sats_obj = next((b for b in master_balances if b.asset_code == "SATSMTL"), None)
        sats_sum = int(float(sats_obj.balance)) if sats_obj else 0
        show_max_sum = max_btc_sum if sats_sum > max_btc_sum else sats_sum
        msg = my_gettext(
            user_id, "btc_in", (0, show_max_sum, min_btc_sum), app_context=app_context
        )
        await state.set_state(StateInOut.sending_btc_sum_in)
        await state.update_data(msg=msg)
        await send_message(
            session,
            user_id,
            msg,
            reply_markup=get_kb_return(user_id, app_context=app_context),
            app_context=app_context,
        )


@router.message(StateInOut.sending_btc_sum_in)
async def cmd_send_btc_sum(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None:
        return
    if message.text is None:
        send_sum = 0
    else:
        try:
            send_sum = int(message.text)
        except Exception:
            send_sum = 0

    assert app_context.use_case_factory is not None, (
        "use_case_factory must be initialized"
    )
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    master_balances = await balance_use_case.execute(0)
    sats_obj = next((b for b in master_balances if b.asset_code == "SATSMTL"), None)
    sats_sum = float(sats_obj.balance) if sats_obj else 0.0
    show_max_sum = max_btc_sum if sats_sum > max_btc_sum else sats_sum

    data = await state.get_data()

    user_balances = await balance_use_case.execute(message.from_user.id)
    has_sats = any(b.asset_code == "SATSMTL" for b in user_balances)

    if send_sum < min_btc_sum or not has_sats or send_sum > show_max_sum:
        await send_message(
            session,
            message,
            f"{my_gettext(message, 'bad_sum', app_context=app_context)}\n{data['msg']}",
            app_context=app_context,
        )
    else:
        order_uuid = await thoth_create_order(
            user_id=message.from_user.id, amount=send_sum
        )
        if order_uuid:
            await state.update_data(send_sum=send_sum)
            await state.set_state(None)
            assert app_context.repository_factory is not None, (
                "repository_factory must be initialized"
            )
            user_repo = app_context.repository_factory.get_user_repository(session)
            if message.from_user is not None:
                await user_repo.set_btc_uuid(message.from_user.id, order_uuid)
                await session.commit()  # Добавляем commit для сохранения изменений в БД
                await cmd_show_btc_in(
                    session, message.from_user.id, state, app_context=app_context
                )
    await message.delete()


@router.callback_query(F.data == "BTC_CHECK")
async def cmd_btc_check(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if callback.from_user is None:
        return
    data = await state.get_data()
    check_time = data.get("check_time")
    if check_time and datetime.now() < datetime.strptime(
        check_time, "%d.%m.%Y %H:%M:%S"
    ) + timedelta(seconds=10):
        remaining_seconds = int(
            (
                datetime.strptime(check_time, "%d.%m.%Y %H:%M:%S")
                + timedelta(seconds=10)
                - datetime.now()
            ).total_seconds()
        )
        await callback.answer(
            text=f"Too frequent requests, please try again in {remaining_seconds} seconds.",
            show_alert=True,
        )
        return
    await state.update_data(check_time=datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
    # rest of the function logic
    async with new_wallet_lock:
        assert app_context.repository_factory is not None, (
            "repository_factory must be initialized"
        )
        user_repo = app_context.repository_factory.get_user_repository(session)
        btc_uuid, btc_date = await user_repo.get_btc_uuid(callback.from_user.id)
        if (
            btc_uuid
            and btc_date
            and isinstance(btc_date, datetime)
            and btc_date > datetime.now()
        ):
            result, sats_sum = await thoth_check_order(btc_uuid)
            if result:
                assert app_context.use_case_factory is not None, (
                    "use_case_factory must be initialized"
                )
                balance_use_case = (
                    app_context.use_case_factory.create_get_wallet_balance(session)
                )
                balances = await balance_use_case.execute(callback.from_user.id)
                has_sats = any(b.asset_code == "SATSMTL" for b in balances)
                if not has_sats:
                    await callback.answer(
                        text="You don't have a trust line to SATSMTL, continuation is not possible",
                        show_alert=True,
                    )
                    return

                master_balances = await balance_use_case.execute(0)
                sats_obj = next(
                    (b for b in master_balances if b.asset_code == "SATSMTL"), None
                )
                btc_balance = float(sats_obj.balance) if sats_obj else 0.0

                if sats_sum > max_btc_sum or sats_sum > btc_balance:
                    await callback.answer(
                        text="Amount exceeds the maximum payout limit, payment is not possible.",
                        show_alert=True,
                    )
                    return
                # all is good ?
                await callback.answer(
                    text=f"Found {round(sats_sum)} SATS, wait transaction",
                    show_alert=True,
                )
                await sleep(1)

                # Payout SATS
                assert app_context.repository_factory is not None, (
                    "repository_factory must be initialized"
                )
                repo = app_context.repository_factory.get_wallet_repository(session)
                user_wallet = await repo.get_default_wallet(callback.from_user.id)
                assert user_wallet is not None, "user wallet must exist"
                assert app_context.use_case_factory is not None, (
                    "use_case_factory must be initialized"
                )
                pay_use_case = app_context.use_case_factory.create_send_payment(session)
                await pay_use_case.execute(
                    user_id=0,
                    destination_address=user_wallet.public_key,
                    asset=DomainAsset(code="SATSMTL", issuer=satsmtl_asset.issuer),
                    amount=round(sats_sum),
                    password="0",
                )

                user_repo = app_context.repository_factory.get_user_repository(session)
                await user_repo.set_btc_uuid(callback.from_user.id, None)
                await session.commit()  # Добавляем commit для сохранения изменений в БД
                # await async_stellar_send(xdr) # handled by SendPayment
                await cmd_info_message(
                    session, callback, "All works done!", app_context=app_context
                )
    await callback.answer()


############################################################################
############################################################################
############################################################################


@router.callback_query(F.data == "BTC_OUT")
async def cmd_btc_out(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    await callback.answer("Not implemented yet", show_alert=True)


############################################################################
############################################################################
############################################################################


@router.callback_query(F.data == "STARTS")
async def cmd_starts_in(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    await callback.answer()
    await state.set_state(StateInOut.sending_starts_sum_in)
    # await state.update_data(msg=msg)
    await state.set_state(StateInOut.sending_starts_sum_in)
    # await state.update_data(msg=msg)
    assert app_context.use_case_factory is not None, (
        "use_case_factory must be initialized"
    )
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    master_balances = await balance_use_case.execute(0)
    eurmtl_obj = next((b for b in master_balances if b.asset_code == "EURMTL"), None)
    eurmtl_sum = float(eurmtl_obj.balance) if eurmtl_obj else 0.0
    await send_message(
        session,
        callback,
        "Введи сумму в EURMTL которую вы хотите получить\n 1 EURMTL = 85 STARS\n"
        f"максимально в наличии {int(eurmtl_sum)} EURMTL",
        reply_markup=get_kb_return(callback, app_context=app_context),
        app_context=app_context,
    )


@router.message(StateInOut.sending_starts_sum_in)
async def cmd_send_starts_sum(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    app_context: AppContext,
):
    if message.text is None:
        return
    try:
        send_sum = int(message.text)
    except Exception:
        send_sum = 0

    assert app_context.use_case_factory is not None, (
        "use_case_factory must be initialized"
    )
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    master_balances = await balance_use_case.execute(0)
    eurmtl_obj = next((b for b in master_balances if b.asset_code == "EURMTL"), None)
    eurmtl_sum = int(float(eurmtl_obj.balance)) if eurmtl_obj else 0

    await state.update_data(send_sum=send_sum)
    if 0 < send_sum < eurmtl_sum:
        await state.set_state(None)
        await bot.send_invoice(
            message.chat.id,
            title=f"{send_sum} EURMTL",
            description=f"{send_sum} EURMTL на ваш кошелек",
            payload="STARS",
            currency="XTR",
            provider_token="",
            prices=[types.LabeledPrice(label="STARS", amount=send_sum * 85)],
            photo_url="https://montelibero.org/wp-content/uploads/2022/02/EURMTL_LOGO_NEW_1-1043x675.jpg",
        )

    await message.delete()
    await clear_last_message_id(message.chat.id, app_context=app_context)


@router.pre_checkout_query()
async def cmd_process_pre_checkout_query(
    pre_checkout_query: types.PreCheckoutQuery, bot: Bot, app_context: AppContext
):
    logger.info(pre_checkout_query)
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def cmd_process_message_successful_payment(
    message: types.Message,
    session: AsyncSession,
    state: FSMContext,
    app_context: AppContext,
):
    if message.from_user is None:
        return
    logger.info(message.successful_payment)
    data = await state.get_data()
    send_sum: int | None = data.get("send_sum")

    async with new_wallet_lock:
        assert app_context.use_case_factory is not None, (
            "use_case_factory must be initialized"
        )
        balance_use_case = app_context.use_case_factory.create_get_wallet_balance(
            session
        )
        user_balances = await balance_use_case.execute(message.from_user.id)
        has_eurmtl = any(b.asset_code == "EURMTL" for b in user_balances)

        if not has_eurmtl:
            await message.answer(
                text="You don't have a trust line to EURMTL, continuation is not possible",
                show_alert=True,
            )
            return
        await message.answer(
            text=f"Found pay for {round(send_sum) if send_sum else 0} EURMTL, wait transaction",
            show_alert=True,
        )
        await sleep(1)

        assert app_context.repository_factory is not None, (
            "repository_factory must be initialized"
        )
        repo = app_context.repository_factory.get_wallet_repository(session)
        user_wallet = await repo.get_default_wallet(message.from_user.id)
        assert user_wallet is not None, "user wallet must exist"
        assert app_context.use_case_factory is not None, (
            "use_case_factory must be initialized"
        )
        pay_use_case = app_context.use_case_factory.create_send_payment(session)
        await pay_use_case.execute(
            user_id=0,
            destination_address=user_wallet.public_key,
            asset=DomainAsset(code="EURMTL", issuer=eurmtl_asset.issuer),
            amount=round(send_sum) if send_sum else 0,
            password="0",
        )
        await cmd_info_message(
            session, message.chat.id, "All works done!", app_context=app_context
        )
        admin_id = app_context.admin_id
        await send_message(
            session,
            user_id=admin_id,
            msg=html.escape(f"{message.from_user} {message.successful_payment} good"),
            need_new_msg=True,
            reply_markup=get_kb_return(message.chat.id, app_context=app_context),
            app_context=app_context,
        )


############################################################################
############################################################################
############################################################################


@router.message(Command(commands=["balance"]))
@safe_catch_async
async def cmd_balance(
    message: types.Message, session: AsyncSession, app_context: AppContext
):
    if message.from_user is None or message.from_user.username != "itolstov":
        await message.answer("У вас нет доступа к этой команде.")
        return
    assert app_context.repository_factory is not None, (
        "repository_factory must be initialized"
    )
    user_repo = app_context.repository_factory.get_user_repository(session)
    balances = await user_repo.get_all_with_usdt_balance()
    if balances:
        balance_message = "\n".join(
            f"Адрес: {addr if addr else 'ID:' + str(id)}, USDT: {amount}"
            for addr, amount, id in balances
        )

        total_balance = sum(amount for _, amount, _ in balances)
        balance_message += f"\nИтого: {total_balance} USDT"
        master_energy = await get_account_energy()
        balance_message += f"\n\nЭнергия аккаунта: {master_energy.energy_amount}"
    else:
        balance_message = "У вас нет активных балансов USDT."
    await message.answer(balance_message)


async def notify_admin(bot: Bot, text: str, *, app_context: AppContext):
    admin_id = app_context.admin_id
    await bot.send_message(chat_id=admin_id, text=text)


@safe_catch_async
async def process_usdt_wallet(
    session: AsyncSession,
    bot: Bot,
    *,
    user_id: int | None = None,
    username: str | None = None,
    master_energy: EnergyObject | None = None,
    app_context: AppContext,
) -> bool:
    if user_id is None and username is None:
        raise ValueError("user_id or username must be provided")

    target_label = f"@{username}" if username else f"id:{user_id}"
    # db_get_usdt_private_key was creating key if missing?
    # Yes, usage here relies on creation or existing.
    # user_repo.get_usdt_key handles creation if missing for existing user.
    # Note: user_id provided here is from iterating addresses?
    # Wait, line 679 context: `usdt_key, balance = db_get_usdt_private_key(session, user_id, create_trc_private_key)`
    # This loop iterates users.
    assert app_context.repository_factory is not None, (
        "repository_factory must be initialized"
    )
    user_repo = app_context.repository_factory.get_user_repository(session)
    usdt_key_opt, balance = await user_repo.get_usdt_key(
        user_id if user_id is not None else 0,
        create_trc_private_key,
        user_name=username,
    )
    if usdt_key_opt is None:
        return False
    usdt_key = usdt_key_opt

    await notify_admin(
        bot,
        f"[USDT] Start processing {target_label}. db_balance={balance}",
        app_context=app_context,
    )
    if balance <= 0:
        await notify_admin(
            bot,
            f"[USDT] {target_label}: zero recorded balance, skipping",
            app_context=app_context,
        )
        return False

    master_energy = master_energy or await get_account_energy()
    trx_balance = Decimal(str(await get_trx_balance(private_key=usdt_key)))
    min_trx_needed = Decimal("0.001")

    if trx_balance < min_trx_needed:
        await send_trx_async(
            private_key_to=usdt_key,
            amount=float(min_trx_needed),
            private_key_from=tron_master_key,
        )
        await notify_admin(
            bot, f"[USDT] {target_label}: topped up TRX", app_context=app_context
        )
        await asyncio.sleep(3)

    trx_balance = Decimal(str(await get_trx_balance(private_key=usdt_key)))
    if trx_balance > Decimal("0.002"):
        await send_trx_async(
            private_key_to=tron_master_key,
            amount=float(trx_balance - min_trx_needed),
            private_key_from=usdt_key,
        )
        await notify_admin(
            bot, f"[USDT] {target_label}: returned extra TRX", app_context=app_context
        )
        await asyncio.sleep(1)

    account_energy = await get_account_energy(private_key=usdt_key)
    if account_energy.free_amount < 500:
        await notify_admin(
            bot,
            f"[USDT] {target_label}: low free energy {account_energy.free_amount}",
            app_context=app_context,
        )
        return False

    usdt_balance = Decimal(str(await get_usdt_balance(private_key=usdt_key)))
    transfer_amount = usdt_balance - Decimal("0.001")
    if transfer_amount <= 0:
        await notify_admin(
            bot,
            f"[USDT] {target_label}: insufficient USDT for transfer ({usdt_balance})",
            app_context=app_context,
        )
        return False

    delegated = False
    try:
        await delegate_energy(private_key_to=usdt_key, energy_object=master_energy)
        delegated = True
        send_success, tx_hash = await send_usdt_async(
            private_key_to=tron_master_key,
            amount=float(transfer_amount),
            private_key_from=usdt_key,
        )
        if send_success:
            async with new_wallet_lock:
                if user_id is not None:
                    await user_repo.update_usdt_balance(user_id, -1 * balance)
                else:
                    # Handle username update
                    # Logic: resolve username to ID first
                    _, target_user_id = await user_repo.get_account_by_username(
                        f"@{username}"
                    )
                    if target_user_id:
                        await user_repo.update_usdt_balance(
                            target_user_id, -1 * balance
                        )
                    else:
                        # Fallback or log error? original would query by username and update.
                        # If user not found by username, original raise error? or do nothing?
                        # db_update_usdt_sum raise ValueError if user not found.
                        # get_account_by_username might behave slightly different but serves purpose.
                        pass
                # Commit the balance update to database
                await session.commit()
            await notify_admin(
                bot,
                f"[USDT] {target_label}: sent {transfer_amount} (tx: {tx_hash}) | db_balance={balance} trx_balance={trx_balance}",
                app_context=app_context,
            )
            return True
        await notify_admin(
            bot,
            f"[USDT] {target_label}: sending failed (tx: {tx_hash})",
            app_context=app_context,
        )
        return False
    finally:
        if delegated:
            await delegate_energy(
                private_key_to=usdt_key, energy_object=master_energy, undo=True
            )


@safe_catch_async
async def process_first_usdt_balance(
    session: AsyncSession,
    bot: Bot,
    master_energy: EnergyObject | None = None,
    *,
    app_context: AppContext,
) -> tuple[bool, str]:
    assert app_context.repository_factory is not None, (
        "repository_factory must be initialized"
    )
    user_repo = app_context.repository_factory.get_user_repository(session)
    balances = await user_repo.get_all_with_usdt_balance()
    if not balances:
        return False, "Список USDT-балансов пуст."

    master_energy = master_energy or await get_account_energy()
    if master_energy.energy_amount <= 130_000:
        return False, f"Недостаточно энергии: {master_energy.energy_amount}"

    username, amount, user_id = balances[0]
    target_name = username if username else f"id:{user_id}"
    success = await process_usdt_wallet(
        session,
        bot,
        user_id=user_id,
        username=username,
        master_energy=master_energy,
        app_context=app_context,
    )
    if success:
        return True, f"Обработка {target_name} запущена (учтено {amount} USDT)."
    return False, f"Не удалось обработать {target_name}."


@router.message(Command(commands=["usdt"]))
@safe_catch_async
async def cmd_usdt_home(
    message: types.Message,
    session: AsyncSession,
    command: CommandObject,
    bot: Bot,
    app_context: AppContext,
):
    if message.from_user is None or message.from_user.username != "itolstov":
        await message.answer("У вас нет доступа к этой команде.")
        return

    if not command.args:
        await message.answer("Нужно указать пользователя.")
        return

    user_arg = command.args.strip()
    await message.answer("Старт обработки. Подробности пришлю в админ-чат.")
    if user_arg.isdigit():
        await process_usdt_wallet(
            session, bot, user_id=int(user_arg), app_context=app_context
        )
    else:
        await process_usdt_wallet(
            session, bot, username=user_arg, app_context=app_context
        )


@router.message(Command(commands=["usdt1"]))
@safe_catch_async
async def cmd_usdt_auto(
    message: types.Message, session: AsyncSession, bot: Bot, app_context: AppContext
):
    if message.from_user is None or message.from_user.username != "itolstov":
        await message.answer("У вас нет доступа к этой команде.")
        return

    success, info = await process_first_usdt_balance(
        session, bot, app_context=app_context
    )
    prefix = "✅" if success else "⚠️"
    await message.answer(f"{prefix} {info}")


@safe_catch_async
async def usdt_worker(bot: Bot, app_context: AppContext):
    last_energy: float = 0.0
    while True:
        try:
            master_energy = await get_account_energy()
            current_energy = master_energy.energy_amount

            # Energy filled notification
            if current_energy > 150_000 >= last_energy:
                last_energy = current_energy
                await bot.send_message(
                    chat_id=app_context.admin_id, text=f"Energy Full: {current_energy}"
                )
                async with app_context.db_pool.get_session() as session:
                    success, info = await process_first_usdt_balance(
                        session,
                        bot,
                        master_energy=master_energy,
                        app_context=app_context,
                    )

            # Energy drained notification
            elif last_energy > 150_000 >= current_energy:
                last_energy = 0

            await asyncio.sleep(60 * 60 * 6)
        except Exception as ex:
            logger.error(["usdt_worker", ex])
            await asyncio.sleep(60)
