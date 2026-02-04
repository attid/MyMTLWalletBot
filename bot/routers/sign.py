import asyncio
from datetime import datetime, timedelta
import jsonpickle  # type: ignore
from aiogram import Router, types, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from stellar_sdk.exceptions import BadRequestError, BaseHorizonError
from aiogram.exceptions import TelegramBadRequest
from sulguk import SULGUK_PARSE_MODE  # type: ignore[import-untyped]
import inspect
import redis.asyncio as aioredis

from infrastructure.services.app_context import AppContext
from other.config_reader import config as app_config

from other.mytypes import MyResponse
from other.web_tools import http_session_manager
from routers.start_msg import cmd_show_balance, cmd_info_message
from infrastructure.utils.telegram_utils import (
    my_gettext,
    send_message,
    cmd_show_sign,
    long_line,
)
from other.web_tools import get_web_decoded_xdr
from keyboards.common_keyboards import get_kb_return, get_return_button
from infrastructure.states import StateSign
from infrastructure.log_models import LogQuery
from shared.constants import REDIS_TX_PREFIX
from other.faststream_tools import publish_pending_tx
from keyboards.webapp import webapp_sign_keyboard


class PinState(StatesGroup):
    sign = State()
    sign_and_send = State()
    set_pin = State()
    set_pin2 = State()
    ask_password = State()
    ask_password_set = State()
    ask_password_set2 = State()


class PinCallbackData(CallbackData, prefix="pin_"):
    action: str


router = Router()
router.message.filter(F.chat.type == "private")

kb_cash: dict[str, types.InlineKeyboardMarkup] = {}


@router.callback_query(F.data == "Yes_send_xdr")
async def cmd_yes_send(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    await state.set_state(PinState.sign_and_send)

    await cmd_ask_pin(session, callback.from_user.id, state, app_context=app_context)
    await callback.answer()


async def cmd_ask_pin(
    session: AsyncSession,
    chat_id: int,
    state: FSMContext,
    msg=None,
    *,
    app_context: AppContext,
):
    data = await state.get_data()
    # Use DI
    user_account_obj = await app_context.stellar_service.get_user_account(
        session, chat_id
    )
    user_account = user_account_obj.account.account_id
    simple_account = user_account[:4] + ".." + user_account[-4:]
    wallet_connect_info = data.get("wallet_connect_info")
    if msg is None:
        msg = data.get("msg")
        if msg is None:
            msg = my_gettext(
                chat_id, "enter_password", (simple_account,), app_context=app_context
            )
            await state.update_data(msg=msg)

    pin_type = data.get("pin_type")
    pin = data.get("pin", "")
    current_state = await state.get_state()

    if pin_type is None:
        repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await repo.get_default_wallet(chat_id)
        pin_type = wallet.use_pin if wallet else 0
        await state.update_data(pin_type=pin_type)

    if pin_type == 1:  # pin
        msg = msg + "\n" + "".ljust(len(pin), "*") + "\n\n" + long_line()
        if current_state == PinState.sign:
            msg += my_gettext(chat_id, "confirm_send_mini_xdr", app_context=app_context)
        if wallet_connect_info:
            msg += wallet_connect_info
        await send_message(
            session,
            chat_id,
            msg,
            reply_markup=get_kb_pin(data, app_context=app_context),
            app_context=app_context,
        )

    if pin_type == 2:  # password
        msg = my_gettext(
            chat_id, "send_password", (simple_account,), app_context=app_context
        )
        if current_state == PinState.sign:
            msg += my_gettext(chat_id, "confirm_send_mini_xdr", app_context=app_context)
        if wallet_connect_info:
            msg += wallet_connect_info
        await state.set_state(PinState.ask_password)
        await send_message(
            session,
            chat_id,
            msg,
            reply_markup=get_kb_return(chat_id, app_context=app_context),
            app_context=app_context,
        )

    if pin_type == 0:  # no password
        await state.update_data(pin=str(chat_id))
        msg = my_gettext(
            chat_id, "confirm_send_mini", (simple_account,), app_context=app_context
        )
        if current_state == PinState.sign:
            msg += my_gettext(chat_id, "confirm_send_mini_xdr", app_context=app_context)
        if wallet_connect_info:
            msg += wallet_connect_info
        await send_message(
            session,
            chat_id,
            msg,
            reply_markup=get_kb_nopassword(chat_id, app_context=app_context),
            app_context=app_context,
        )

    if pin_type == 10:  # без ключа - WebApp подписание
        await state.update_data(pin="ro")
        xdr = data.get("xdr")
        memo = data.get("operation", "Transaction")

        # Публикуем TX в Redis для WebApp
        tx_id = await publish_pending_tx(
            user_id=chat_id,
            wallet_address=user_account,
            unsigned_xdr=xdr,
            memo=memo,
        )

        # Показываем кнопку WebApp
        text = my_gettext(chat_id, 'biometric_sign_prompt', app_context=app_context)
        if text == 'biometric_sign_prompt':
            text = f"Подтвердите транзакцию:\n\n{memo}"

        await send_message(
            session,
            chat_id,
            text,
            reply_markup=webapp_sign_keyboard(tx_id),
            app_context=app_context,
        )


def get_kb_pin(data: dict, app_context: AppContext) -> types.InlineKeyboardMarkup:
    # Need to consider if caching is safe with app_context if it matters...
    # Assuming user_lang is enough key.
    if data["user_lang"] in kb_cash:
        return kb_cash[data["user_lang"]]
    else:
        buttons_list = [
            ["1", "2", "3", "A"],
            ["4", "5", "6", "B"],
            ["7", "8", "9", "C"],
            ["0", "D", "E", "F"],
            ["Del", "Enter"],
        ]

        kb_buttons = []

        for buttons in buttons_list:
            tmp_buttons = []
            for button in buttons:
                tmp_buttons.append(
                    types.InlineKeyboardButton(
                        text=button, callback_data=PinCallbackData(action=button).pack()
                    )
                )
            kb_buttons.append(tmp_buttons)

        kb_buttons.append(get_return_button(data["user_lang"], app_context=app_context))
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=kb_buttons)
        kb_cash[data["user_lang"]] = keyboard
        return keyboard


@router.callback_query(PinCallbackData.filter())
async def cq_pin(
    query: types.CallbackQuery,
    callback_data: PinCallbackData,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    answer = callback_data.action
    user_id = query.from_user.id
    data = await state.get_data()
    pin = data.get("pin", "")
    current_state = await state.get_state()

    if answer in "1234567890ABCDEF":
        pin += answer
        await state.update_data(pin=pin)
        await cmd_ask_pin(session, user_id, state, app_context=app_context)
        await query.answer("".ljust(len(pin), "*"))
        if current_state in (PinState.sign, PinState.sign_and_send):  # sign and send
            try:
                # Use DI
                await app_context.stellar_service.get_user_keypair(
                    session, user_id, pin
                )  # test pin
                await sign_xdr(session, state, user_id, app_context=app_context)
            except Exception:
                pass

    if answer == "Del":
        pin = pin[: len(pin) - 1]
        await state.update_data(pin=pin)
        await cmd_ask_pin(session, user_id, state, app_context=app_context)
        await query.answer("".ljust(len(pin), "*"))

    if answer == "Enter":
        if current_state == PinState.set_pin:  # ask for save need pin2
            await state.update_data(pin2=pin, pin="")
            await state.set_state(PinState.set_pin2)
            await cmd_ask_pin(
                session,
                user_id,
                state,
                my_gettext(user_id, "resend_password", app_context=app_context),
                app_context=app_context,
            )
        if current_state == PinState.set_pin2:  # ask pin2 for save
            pin2 = data.get("pin2", "")
            # public_key = data.get('public_key', '')
            await state.set_state(None)
            pin_type = data.get("pin_type", "")

            if pin == pin2:
                # Use DI
                await app_context.stellar_service.change_password(
                    session, user_id, str(user_id), pin, pin_type
                )
                await cmd_show_balance(session, user_id, state, app_context=app_context)
            else:
                await state.update_data(pin2="", pin="")
                await state.set_state(PinState.set_pin)
                await query.answer(
                    my_gettext(user_id, "bad_passwords", app_context=app_context),
                    show_alert=True,
                )
        if current_state in (PinState.sign, PinState.sign_and_send):  # sign and send
            try:
                # Use DI
                await app_context.stellar_service.get_user_keypair(
                    session, user_id, pin
                )  # test pin
                await sign_xdr(session, state, user_id, app_context=app_context)
            except Exception:
                await query.answer(
                    my_gettext(user_id, "bad_password", app_context=app_context),
                    show_alert=True,
                )
                return True
        return True


@router.message(StateFilter(PinState.sign, PinState.sign_and_send))
async def cmd_password_from_pin(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.text is None or message.from_user is None:
        return
    pin = message.text.upper()
    user_id = message.from_user.id
    await state.update_data(pin=pin)
    await message.delete()
    await cmd_ask_pin(session, user_id, state, app_context=app_context)
    try:
        # Use DI
        await app_context.stellar_service.get_user_keypair(
            session, user_id, pin
        )  # test pin
        await sign_xdr(session, state, user_id, app_context=app_context)
    except Exception:
        pass


async def sign_xdr(session: AsyncSession, state, user_id, *, app_context: AppContext):
    data = await state.get_data()
    current_state = await state.get_state()
    pin = data.get("pin", "")
    await state.set_state(None)
    xdr = data.get("xdr")
    fsm_func = data.get("fsm_func")
    fsm_after_send = data.get("fsm_after_send")
    try:
        if user_id > 0:
            if fsm_func:
                fsm_func = jsonpickle.loads(fsm_func)
                # Safely pass app_context if supported
                kwargs = {}
                sig = inspect.signature(fsm_func)
                if "app_context" in sig.parameters or any(
                    p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
                ):
                    kwargs["app_context"] = app_context

                await fsm_func(session, user_id, state, **kwargs)
            else:
                # Use DI
                xdr = await app_context.stellar_service.user_sign(
                    session, xdr, user_id, str(pin)
                )
                await state.set_state(None)
                await state.update_data(xdr=xdr)
                if current_state == PinState.sign_and_send:
                    await state.update_data(
                        try_sent_xdr=(datetime.now() + timedelta(minutes=5)).strftime(
                            "%d.%m.%Y %H:%M:%S"
                        )
                    )
                    await cmd_info_message(
                        session,
                        user_id,
                        my_gettext(user_id, "try_send", app_context=app_context),
                        app_context=app_context,
                    )
                    # save_xdr_to_send(user_id, xdr)
                    # Use DI
                    resp = await app_context.stellar_service.send_xdr_async(xdr)
                    my_resp = MyResponse.from_dict(resp)
                    await state.update_data(try_sent_xdr=None)
                    link_msg = ""
                    if my_resp.paging_token:
                        link_msg = f'\n(<a href="https://viewer.eurmtl.me/transaction/{my_resp.hash}">viewer</a>)'

                    msg = (
                        my_gettext(user_id, "send_good", app_context=app_context)
                        + link_msg
                    )

                    success_msg = data.get("success_msg")
                    if success_msg:
                        msg = msg + "\n\n" + success_msg

                    await cmd_info_message(
                        session, user_id, msg, app_context=app_context
                    )
                    if success_msg:
                        await state.update_data(last_message_id=0)

                    if fsm_after_send:
                        fsm_after_send = jsonpickle.loads(fsm_after_send)
                        # Safely pass app_context if supported
                        kwargs = {}
                        sig = inspect.signature(fsm_after_send)
                        if "app_context" in sig.parameters or any(
                            p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
                        ):
                            kwargs["app_context"] = app_context

                        await fsm_after_send(session, user_id, state, **kwargs)
                if current_state == PinState.sign:
                    await cmd_show_sign(
                        session,
                        user_id,
                        state,
                        my_gettext(
                            user_id, "your_xdr_sign", (xdr,), app_context=app_context
                        ),
                        use_send=True,
                        app_context=app_context,
                    )

                log_queue = app_context.log_queue
                log_queue.put_nowait(
                    LogQuery(
                        user_id=user_id,
                        log_operation="sign",
                        log_operation_info=data.get("operation", ""),
                    )
                )

    except BadRequestError as ex:
        extras = ex.extras.get("result_codes", "no extras") if ex.extras else ex.detail
        msg = f"{ex.title}, error {ex.status}, {extras}"
        logger.info(["BadRequestError", msg, current_state])
        await cmd_info_message(
            session,
            user_id,
            f"{my_gettext(user_id, 'send_error', app_context=app_context)}\n{msg}",
            resend_transaction=True,
            app_context=app_context,
        )
        await state.update_data(try_sent_xdr=None)
    except BaseHorizonError as ex:
        extras = ex.extras.get("result_codes", "no extras") if ex.extras else ex.detail
        msg = f"{ex.title}, error {ex.status}, {extras}"
        logger.info(["BaseHorizonError", msg, current_state])
        await cmd_info_message(
            session,
            user_id,
            f"{my_gettext(user_id, 'send_error', app_context=app_context)}\n{msg}",
            resend_transaction=True,
            app_context=app_context,
        )
        await state.update_data(try_sent_xdr=None)
    except TimeoutError as ex:
        logger.info(["TimeoutError", ex, current_state])
        await cmd_info_message(
            session, user_id, "timeout error =( ", app_context=app_context
        )
    except Exception as ex:
        logger.info(["ex", ex, current_state])
        await cmd_info_message(
            session,
            user_id,
            my_gettext(user_id, "bad_password", app_context=app_context),
            app_context=app_context,
        )
    repo = app_context.repository_factory.get_wallet_repository(session)
    await repo.reset_balance_cache(user_id)
    await session.commit()
    await state.update_data(pin="")


def get_kb_nopassword(
    chat_id: int, app_context: AppContext
) -> types.InlineKeyboardMarkup:
    buttons = [
        [
            types.InlineKeyboardButton(
                text=my_gettext(chat_id, "kb_yes_do", app_context=app_context),
                callback_data=PinCallbackData(action="Enter").pack(),
            )
        ],
        get_return_button(chat_id, app_context=app_context),
    ]

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


@router.callback_query(F.data == "Sign")
async def cmd_sign(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    await cmd_show_sign(
        session,
        callback.from_user.id,
        state,
        my_gettext(callback, "send_xdr", app_context=app_context),
        app_context=app_context,
    )
    await state.set_state(StateSign.sending_xdr)
    await state.update_data(part_xdr="")
    try:
        await callback.answer()
    except TelegramBadRequest:
        pass


@router.message(StateSign.sending_xdr)
async def cmd_send_xdr(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.text is None or message.from_user is None:
        return
    await cmd_check_xdr(
        session, message.text, message.from_user.id, state, app_context=app_context
    )
    await message.delete()


async def cmd_check_xdr(
    session: AsyncSession,
    check_xdr: str,
    user_id,
    state: FSMContext,
    *,
    app_context: AppContext,
):
    try:
        data = await state.get_data()
        part_xdr = data.get("part_xdr", "")
        if part_xdr is None:
            part_xdr = ""

        if len(check_xdr) >= 4096:
            # possible we have xdr in 2\3 message
            part_xdr = part_xdr + check_xdr
            await state.update_data(part_xdr=part_xdr)
            await asyncio.sleep(3)

            data = await state.get_data()
            part_xdr = data.get("part_xdr", "")
            if part_xdr is None:
                part_xdr = ""
            if len(part_xdr) == 0:
                return
            check_xdr = part_xdr

        # else:
        if part_xdr:
            check_xdr = part_xdr + check_xdr
            await state.update_data(part_xdr="")

        ####
        # Use DI
        is_free = await app_context.stellar_service.is_free_wallet(session, user_id)
        xdr = await app_context.stellar_service.check_xdr(
            check_xdr, for_free_account=is_free
        )
        if xdr:
            await state.update_data(xdr=xdr)
            if check_xdr.find("eurmtl.me/sign_tools") > -1:
                await state.update_data(tools=check_xdr, operation="sign_tools")
            await state.set_state(PinState.sign)
            await cmd_ask_pin(session, user_id, state, app_context=app_context)
        else:
            raise Exception("Bad xdr")
    except Exception as ex:
        logger.info(["my_state == MyState.StateSign", ex])
        await cmd_show_sign(
            session,
            user_id,
            state,
            my_gettext(user_id, "bad_xdr", (check_xdr,), app_context=app_context),
            app_context=app_context,
        )


@router.callback_query(F.data == "SendTr")
@router.callback_query(F.data == "SendTools")
async def cmd_show_send_tr(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    data = await state.get_data()
    callback_url = data.get("callback_url")
    xdr = data.get("xdr")
    wallet_connect = data.get("wallet_connect")
    user_id = callback.from_user.id
    try:
        if callback.data == "SendTools":
            if callback_url:
                try:
                    response = await http_session_manager.get_web_request(
                        "POST", url=callback_url, data={"xdr": xdr}
                    )

                    logger.debug(f"Callback response: {response.data}")
                    if response.status == 200:
                        return_url = data.get("return_url")
                        if return_url:
                            # Если есть return_url, отправляем только SUCCESS с кнопкой возврата
                            from keyboards.common_keyboards import get_kb_return_url

                            await send_message(
                                session,
                                callback.from_user.id,
                                "SUCCESS",
                                reply_markup=get_kb_return_url(
                                    callback.from_user.id,
                                    return_url,
                                    app_context=app_context,
                                ),
                                app_context=app_context,
                            )
                        else:
                            await cmd_info_message(
                                session, callback, "SUCCESS", app_context=app_context
                            )
                    else:
                        await cmd_info_message(
                            session, callback, "ERROR", app_context=app_context
                        )
                except Exception as ex:
                    logger.info(["cmd_show_send_tr", callback, ex])
                    await cmd_info_message(
                        session,
                        callback,
                        my_gettext(callback, "send_error", app_context=app_context),
                        app_context=app_context,
                    )
            elif wallet_connect:
                try:
                    wallet_connect_func = jsonpickle.loads(wallet_connect)
                    # Safely pass app_context if supported
                    kwargs = {}
                    sig = inspect.signature(wallet_connect_func)
                    if "app_context" in sig.parameters or any(
                        p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
                    ):
                        kwargs["app_context"] = app_context
                    await wallet_connect_func(session, user_id, state, **kwargs)

                except Exception as ex:
                    logger.info(["cmd_show_send_tr", callback, ex])

            else:
                try:
                    response = await http_session_manager.get_web_request(
                        "POST",
                        url="https://eurmtl.me/remote/update_signature",
                        json={"xdr": xdr},
                    )

                    # status, response_json = await get_web_request('POST', url='https://eurmtl.me/remote/update_signature',
                    #                                               json={"xdr": xdr})
                    # { "SUCCESS": true/false, "MESSAGES": ["список", "сообщений", "об", "обработке"] }
                    if isinstance(response.data, dict):
                        msgs = "\n".join(response.data.get("MESSAGES", []))
                        if response.data.get("SUCCESS"):
                            return_url = data.get("return_url")
                            if return_url:
                                from keyboards.common_keyboards import get_kb_return_url

                                await send_message(
                                    session,
                                    callback.from_user.id,
                                    "SUCCESS",
                                    reply_markup=get_kb_return_url(
                                        callback.from_user.id,
                                        return_url,
                                        app_context=app_context,
                                    ),
                                    app_context=app_context,
                                )
                                return
                            else:
                                await cmd_info_message(
                                    session,
                                    callback,
                                    f"SUCCESS\n{msgs}",
                                    app_context=app_context,
                                )
                        else:
                            await cmd_info_message(
                                session,
                                callback,
                                f"ERROR\n{msgs}",
                                app_context=app_context,
                            )
                    else:
                        await cmd_info_message(
                            session,
                            callback,
                            f"ERROR: {response.data}",
                            app_context=app_context,
                        )

                except Exception as ex:
                    logger.info(["cmd_show_send_tr", callback, ex])
                    await cmd_info_message(
                        session,
                        callback,
                        my_gettext(callback, "send_error", app_context=app_context),
                        app_context=app_context,
                    )
        else:
            await cmd_info_message(
                session,
                callback,
                my_gettext(callback, "try_send", app_context=app_context),
                app_context=app_context,
            )
            # save_xdr_to_send(callback.from_user.id, xdr)
            # Use DI
            assert xdr is not None, "xdr must not be None"
            await app_context.stellar_service.send_xdr_async(xdr)
            return_url = data.get("return_url")
            if return_url:
                from keyboards.common_keyboards import get_kb_return_url

                await send_message(
                    session,
                    callback.from_user.id,
                    "SUCCESS",
                    reply_markup=get_kb_return_url(
                        callback.from_user.id, return_url, app_context=app_context
                    ),
                    app_context=app_context,
                )
                return
            else:
                await cmd_info_message(
                    session,
                    callback,
                    my_gettext(callback, "send_good", app_context=app_context),
                    app_context=app_context,
                )
    except BaseHorizonError as ex:
        logger.info(["send BaseHorizonError", ex])
        msg = f"{ex.title}, error {ex.status}"
        # Try to get human-readable Stellar error
        error_hint = ""
        if hasattr(ex, "extras") and ex.extras and ex.extras.get("result_codes"):
            try:
                from other.stellar_error_codes import get_stellar_error_message

                error_hint = get_stellar_error_message(ex.extras["result_codes"])
            except Exception:
                error_hint = ""
        if error_hint:
            msg = f"{msg}\n<b>{error_hint}</b>"
        await cmd_info_message(
            session,
            callback,
            f"{my_gettext(callback, 'send_error', app_context=app_context)}\n{msg}",
            resend_transaction=True,
            app_context=app_context,
        )
    except Exception as ex:
        logger.exception(["send unknown error", ex])
        msg = "unknown error"
        if xdr:
            data["xdr_error"] = xdr
        await cmd_info_message(
            session,
            callback,
            f"{my_gettext(callback, 'send_error', app_context=app_context)}\n{msg}",
            resend_transaction=True,
            app_context=app_context,
        )


@router.message(PinState.ask_password)
async def cmd_password(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None:
        return
    await state.update_data(pin=message.text)
    await message.delete()
    await state.set_state(PinState.sign_and_send)
    await sign_xdr(session, state, message.from_user.id, app_context=app_context)


@router.message(PinState.ask_password_set)
async def cmd_password_set(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None:
        return
    await state.update_data(pin=message.text)
    await state.set_state(PinState.ask_password_set2)
    await message.delete()
    await send_message(
        session,
        message,
        my_gettext(message, "resend_password", app_context=app_context),
        reply_markup=get_kb_return(message.from_user.id, app_context=app_context),
        app_context=app_context,
    )


@router.message(PinState.ask_password_set2)
async def cmd_password_set2(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None:
        return
    data = await state.get_data()
    user_id = message.from_user.id
    pin = data.get("pin", "")
    # public_key = data.get('public_key', '')
    if data["pin"] == message.text:
        await state.set_state(None)
        pin_type = data.get("pin_type", "")
        # Use DI
        await app_context.stellar_service.change_password(
            session, user_id, str(user_id), pin, pin_type
        )
        await cmd_show_balance(session, user_id, state, app_context=app_context)
        await state.update_data(pin2="", pin="")
        await message.delete()
    else:
        if message.from_user is None:
            return
        await message.delete()
        await state.set_state(PinState.ask_password_set)
        await send_message(
            session,
            message,
            my_gettext(message, "bad_passwords", app_context=app_context),
            reply_markup=get_kb_return(message.from_user.id, app_context=app_context),
            app_context=app_context,
        )


@router.callback_query(F.data == "ReSend")
async def cmd_resend(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    data = await state.get_data()
    xdr = data.get("xdr")
    user_id = callback.from_user.id
    try:
        await cmd_info_message(
            session,
            user_id,
            my_gettext(user_id, "resend", app_context=app_context),
            app_context=app_context,
        )
        # Use DI
        assert xdr is not None, "xdr must not be None"
        await app_context.stellar_service.send_xdr_async(xdr)
        await cmd_info_message(
            session,
            user_id,
            my_gettext(user_id, "send_good", app_context=app_context),
            app_context=app_context,
        )
    except BaseHorizonError as ex:
        logger.info(["ReSend BaseHorizonError", ex])
        msg = f"{ex.title}, error {ex.status}"
        # Try to get human-readable Stellar error
        error_hint = ""
        if hasattr(ex, "extras") and ex.extras and ex.extras.get("result_codes"):
            try:
                from other.stellar_error_codes import get_stellar_error_message

                error_hint = get_stellar_error_message(ex.extras["result_codes"])
            except Exception:
                error_hint = ""
        if error_hint:
            msg = f"{msg}\n<b>{error_hint}</b>"
        await cmd_info_message(
            session,
            user_id,
            f"{my_gettext(user_id, 'send_error', app_context=app_context)}\n{msg}",
            resend_transaction=True,
            app_context=app_context,
        )
    except Exception as ex:
        logger.info(["ReSend unknown error", ex])
        msg = "unknown error"
        data = await state.get_data()
        if xdr:
            data["xdr_error"] = xdr
        await cmd_info_message(
            session,
            user_id,
            f"{my_gettext(user_id, 'send_error', app_context=app_context)}\n{msg}",
            resend_transaction=True,
            app_context=app_context,
        )


@router.callback_query(F.data == "Decode")
async def cmd_decode_xdr(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    data = await state.get_data()
    xdr = data.get("xdr")

    msg = await get_web_decoded_xdr(xdr)

    # msg = msg.replace("&nbsp;", "\u00A0")
    await cmd_show_sign(
        session,
        callback.from_user.id,
        state,
        msg[:4000],
        use_send=True,
        parse_mode=SULGUK_PARSE_MODE,
        app_context=app_context,
    )


@router.callback_query(F.data.startswith("cancel_biometric_sign:"))
async def cmd_cancel_biometric_sign(
    callback: types.CallbackQuery,
    session: AsyncSession,
    app_context: AppContext,
):
    """Отмена биометрического подписания транзакции."""
    tx_id = callback.data.split(":")[1]
    user_id = callback.from_user.id

    # Удаляем TX из Redis
    redis_client = aioredis.from_url(app_config.redis_url)
    try:
        tx_key = f"{REDIS_TX_PREFIX}{tx_id}"
        deleted = await redis_client.delete(tx_key)

        if deleted:
            logger.info(f"User {user_id} cancelled biometric signing for TX {tx_id}")
            await callback.answer(
                my_gettext(user_id, "sign_cancelled", app_context=app_context)
                if my_gettext(user_id, "sign_cancelled", app_context=app_context) != "sign_cancelled"
                else "Подписание отменено",
                show_alert=True,
            )
        else:
            logger.warning(f"TX {tx_id} not found in Redis (already expired or processed)")
            await callback.answer(
                my_gettext(user_id, "sign_expired", app_context=app_context)
                if my_gettext(user_id, "sign_expired", app_context=app_context) != "sign_expired"
                else "Транзакция истекла или уже обработана",
                show_alert=True,
            )
    finally:
        await redis_client.aclose()

    # Удаляем сообщение с кнопкой
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "cancel_import_key")
async def cmd_cancel_import_key(
    callback: types.CallbackQuery,
    app_context: AppContext,
):
    """Отмена импорта ключа."""
    user_id = callback.from_user.id
    logger.info(f"User {user_id} cancelled key import")

    await callback.answer(
        my_gettext(user_id, "import_cancelled", app_context=app_context)
        if my_gettext(user_id, "import_cancelled", app_context=app_context) != "import_cancelled"
        else "Импорт отменён",
        show_alert=True,
    )

    # Удаляем сообщение с кнопкой
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
