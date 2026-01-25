from typing import List, Union

import jsonpickle  # type: ignore
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from stellar_sdk import Asset
from stellar_sdk.sep.federation import resolve_stellar_address
from infrastructure.services.app_context import AppContext


from keyboards.common_keyboards import (
    get_kb_return,
    get_return_button,
    get_kb_yesno_send_xdr,
    get_kb_offers_cancel,
)


from other.lang_tools import check_user_id
from other.mytypes import Balance
from routers.sign import cmd_check_xdr
from infrastructure.utils.telegram_utils import (
    my_gettext,
    send_message,
    check_username,
    clear_state,
    clear_last_message_id,
    TELEGRAM_API_ERROR,
)  # Импортируем TELEGRAM_API_ERROR
from infrastructure.utils.common_utils import get_user_id
from infrastructure.utils.common_utils import decode_qr_code
from routers.uri import handle_wc_uri

from infrastructure.utils.common_utils import float2str
from infrastructure.utils.stellar_utils import (
    parse_pay_stellar_uri,
    is_valid_stellar_address,
    my_float,
    cut_text_to_28_bytes,
    eurmtl_asset,
)
from other.stellar_tools import stellar_check_account, get_first_balance_from_list


class StateSendToken(StatesGroup):
    sending_for = State()
    sending_sum = State()
    sending_memo = State()


class SendAssetCallbackData(CallbackData, prefix="send_asset_"):
    answer: str


router = Router()
router.message.filter(F.chat.type == "private")


def get_kb_send(
    user_id: Union[types.CallbackQuery, types.Message, int], *, app_context: AppContext
) -> types.InlineKeyboardMarkup:
    user_id = get_user_id(user_id)

    buttons = [
        [
            types.InlineKeyboardButton(
                text=my_gettext(user_id, "kb_choose", app_context=app_context),
                switch_inline_query_current_chat="",
            )
        ],
        get_return_button(user_id, app_context=app_context),
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


async def cmd_send_start(
    user_id: int, state: FSMContext, session: AsyncSession, *, app_context: AppContext
):
    msg = my_gettext(user_id, "send_address", app_context=app_context)
    await clear_state(state)
    # keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True,
    #                                     keyboard=[[types.KeyboardButtonRequestUser()]])
    # await send_message(session,user_id, msg, reply_markup=keyboard)
    await send_message(
        session,
        user_id,
        msg,
        reply_markup=get_kb_send(user_id, app_context=app_context),
        app_context=app_context,
    )
    await state.set_state(StateSendToken.sending_for)


@router.callback_query(F.data == "Send")
async def cmd_send_callback(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if not callback.from_user:
        return
    await cmd_send_start(callback.from_user.id, state, session, app_context=app_context)
    await callback.answer()


@router.message(Command(commands=["send"]))
async def cmd_send_message(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if not message.from_user:
        return
    await message.delete()
    await cmd_send_start(message.from_user.id, state, session, app_context=app_context)


async def cmd_send_token(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    send_for: str,
    send_asset: Asset,
    send_sum: float,
    send_memo: Union[str, None] = None,
    *,
    app_context: AppContext,
):
    if message.from_user is None:
        return
    try:
        if "@" == send_for[0]:
            # from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
            user_repo = app_context.repository_factory.get_user_repository(session)
            send_address, user_id = await user_repo.get_account_by_username(send_for)
            # Получаем текущее имя пользователя из базы данных для сравнения
            if user_id is None:
                raise Exception("user not found")
            user_in_db = await user_repo.get_by_id(user_id)
            current_username_in_db = user_in_db.username if user_in_db else None

            tmp_name = await check_username(user_id, app_context=app_context)

            if tmp_name is TELEGRAM_API_ERROR:
                user_id_to_notify = get_user_id(message)
                logger.error(
                    f"cmd_send_token: Telegram API error when checking username for user_id={user_id}. Searched: {send_for}"
                )
                await send_message(
                    session,
                    user_id_to_notify,
                    my_gettext(
                        user_id_to_notify, "telegram_api_error", app_context=app_context
                    ),
                    reply_markup=get_kb_return(message, app_context=app_context),
                    app_context=app_context,
                )
                return  # Прерываем выполнение, так как не можем проверить username

            # Сравниваем tmp_name (фактический username) с send_for (ожидаемый username)
            # и с current_username_in_db (username в базе)
            # Обновляем username в базе только если фактический username изменился по сравнению с тем, что в базе
            # или если в базе username отсутствует, а фактический есть (или наоборот)
            actual_username_lower: str | None = (
                tmp_name.lower() if isinstance(tmp_name, str) and tmp_name else None
            )
            send_for_lower = send_for.lower()[1:]
            current_username_in_db_lower = (
                current_username_in_db.lower() if current_username_in_db else None
            )

            if actual_username_lower != current_username_in_db_lower:
                logger.warning(
                    f"cmd_send_token: username in DB needs update: searched/expected={send_for}, actual_telegram_username={tmp_name}, in_db={current_username_in_db}, user_id={user_id}"
                )
                update_profile = (
                    app_context.use_case_factory.create_update_user_profile(session)
                )
                await update_profile.execute(user_id=user_id, username=tmp_name)
                await session.commit()

            # Проверяем, совпадает ли актуальный username с тем, на который хотят отправить
            if actual_username_lower is None or actual_username_lower != send_for_lower:
                logger.warning(
                    f"cmd_send_token: username mismatch for send operation: searched/expected={send_for}, actual_telegram_username={tmp_name}, user_id={user_id}"
                )
                raise Exception(
                    "Имя пользователя не совпадает"
                )  # Это исключение будет обработано ниже

            logger.info(
                f"cmd_send_token: username resolved: searched={send_for}, address={send_address}, user_id={user_id}"
            )
        else:
            send_address = send_for
            logger.info(f"cmd_send_token: address used directly: {send_address}")
        if send_address is None:
            raise Exception("send_address is None")
        await stellar_check_account(send_address)
    except Exception as ex:
        user_id_to_notify = get_user_id(message)
        logger.error(
            f"cmd_send_token: failed to resolve address. Searched: {send_for}, Exception: {ex}"
        )
        await send_message(
            session,
            user_id_to_notify,
            my_gettext(user_id_to_notify, "send_error2", app_context=app_context),
            reply_markup=get_kb_return(message, app_context=app_context),
            app_context=app_context,
        )
        return

    await state.update_data(
        send_sum=send_sum,
        send_address=send_address,
        send_asset_code=send_asset.code,
        send_asset_issuer=send_asset.issuer,
        # mtlap_stars=mtlap_stars todo нужно ли?
    )

    if send_memo:
        await state.update_data(memo=send_memo, federal_memo=True)

    await cmd_send_04(session, message, state, app_context=app_context)


@router.message(Command(commands=["eurmtl"]))
async def cmd_eurmtl(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    await clear_state(state)
    chat_id = get_user_id(message)
    await clear_last_message_id(chat_id, app_context=app_context)

    parts = message.text.split() if message.text else []
    if len(parts) < 3:
        await send_message(
            session,
            chat_id,
            "Invalid command format. Usage: /eurmtl @username|address amount [memo]",
            app_context=app_context,
        )
        return

    try:
        send_for = parts[1]
        amount = float(parts[2])
    except ValueError:
        await send_message(
            session,
            chat_id,
            "Invalid amount. Please enter a numerical value.",
            app_context=app_context,
        )
        return

    memo = " ".join(parts[3:]) if len(parts) > 3 else None

    # Call the cmd_send_token function with provided details
    await cmd_send_token(
        message=message,
        state=state,
        session=session,
        send_for=send_for,
        send_asset=eurmtl_asset,
        send_sum=amount,
        send_memo=memo,
        app_context=app_context,
    )


@router.message(Command(commands=["start"]), F.text.contains("eurmtl_"))
async def cmd_start_eurmtl(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    await message.delete()
    await clear_state(state)

    # check address
    user_id = get_user_id(message)
    await state.update_data(last_message_id=0)
    await send_message(session, user_id, "Loading", app_context=app_context)

    # if user not exist
    if not await check_user_id(session, user_id):
        await send_message(
            session,
            user_id,
            "You dont have wallet. Please run /start",
            app_context=app_context,
        )
        return

    # Parse the start command
    parts = message.text.split("eurmtl_")[1].strip().split("-") if message.text else []
    if len(parts) < 2:
        await send_message(
            session, user_id, "Invalid command format", app_context=app_context
        )
        return

    username = parts[0]
    try:
        amount = float(parts[1])
    except ValueError:
        if message.from_user is None:
            return
        await send_message(
            session, message.from_user.id, "Invalid amount", app_context=app_context
        )
        return

    memo = " ".join(parts[2:]) if len(parts) > 2 else None

    # Convert username to Stellar address
    try:
        send_for = "@" + username
        # from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
        user_repo = app_context.repository_factory.get_user_repository(session)
        stellar_address, _ = await user_repo.get_account_by_username(send_for)
    except Exception as ex:
        if message.from_user is None:
            return
        await send_message(
            session, message.from_user.id, f"Error: {str(ex)}", app_context=app_context
        )
        return

    # Call the cmd_send_token function
    if stellar_address is None:
        raise Exception("stellar_address is None")
    await cmd_send_token(
        message,
        state,
        session,
        stellar_address,
        eurmtl_asset,
        amount,
        memo,
        app_context=app_context,
    )


@router.message(StateSendToken.sending_for, F.text)
async def cmd_send_for(
    message: Message, state: FSMContext, session: AsyncSession, app_context: AppContext
):
    if message.from_user is None:
        return
    data = await state.get_data()
    send_for_input = data.get(
        "qr", message.text
    )  # Используем send_for_input для ясности

    if send_for_input and "@" == send_for_input[0]:
        try:
            # from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
            user_repo = app_context.repository_factory.get_user_repository(session)
            public_key, user_id = await user_repo.get_account_by_username(
                send_for_input
            )
            if user_id is None:
                raise Exception("user not found")
            user_in_db = await user_repo.get_by_id(user_id)
            current_username_in_db = user_in_db.username if user_in_db else None

            tmp_name = await check_username(user_id, app_context=app_context)

            if tmp_name is TELEGRAM_API_ERROR:
                logger.error(
                    f"StateSendFor: Telegram API error when checking username for user_id={user_id}. Searched: {send_for_input}"
                )
                await send_message(
                    session,
                    message.chat.id,
                    my_gettext(
                        message.chat.id, "telegram_api_error", app_context=app_context
                    ),
                    reply_markup=get_kb_return(message, app_context=app_context),
                    app_context=app_context,
                )
                return

            actual_username_lower: str | None = (
                tmp_name.lower() if isinstance(tmp_name, str) and tmp_name else None
            )
            send_for_input_lower = send_for_input.lower()[1:]
            current_username_in_db_lower = (
                current_username_in_db.lower() if current_username_in_db else None
            )

            if actual_username_lower != current_username_in_db_lower:
                logger.warning(
                    f"StateSendFor: username in DB needs update: searched/expected={send_for_input}, actual_telegram_username={tmp_name}, in_db={current_username_in_db}, user_id={user_id}"
                )
                update_profile = (
                    app_context.use_case_factory.create_update_user_profile(session)
                )
                await update_profile.execute(user_id=user_id, username=tmp_name)
                await session.commit()

            if actual_username_lower != send_for_input_lower:
                logger.warning(
                    f"StateSendFor: username mismatch for send operation: searched/expected={send_for_input}, actual_telegram_username={tmp_name}, user_id={user_id}"
                )
                raise Exception("Имя пользователя не совпадает")

            logger.info(
                f"StateSendFor: username resolved: searched={send_for_input}, address={public_key}, user_id={user_id}"
            )
        except Exception as ex:
            logger.error(
                f"StateSendFor: failed to resolve username. Searched: {send_for_input}, Exception: {ex}"
            )
            await send_message(
                session,
                message.chat.id,
                my_gettext(message.chat.id, "send_error2", app_context=app_context),
                reply_markup=get_kb_return(message, app_context=app_context),
                app_context=app_context,
            )
            return
    else:
        public_key = data.get("qr", message.text)
        logger.info(f"StateSendFor: address used directly: {public_key}")
    if public_key is None:
        return
    my_account = await stellar_check_account(public_key)
    if my_account:
        await state.update_data(send_address=my_account.account_id)
        if my_account.memo:
            await state.update_data(memo=my_account.memo, federal_memo=True)

        await state.set_state(None)
        await cmd_send_choose_token(message, state, session, app_context=app_context)
    else:
        wallet_repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await wallet_repo.get_default_wallet(message.from_user.id)
        free_wallet = wallet.is_free if wallet else False
        address = data.get("qr", message.text)
        if address and isinstance(address, str) and address.find("*") > 0:
            try:
                address = resolve_stellar_address(address).account_id
            except Exception as ex:
                logger.error(
                    f"StateSendFor: failed to resolve stellar address. Searched: {address}, Exception: {ex}"
                )
        if (
            address
            and isinstance(address, str)
            and (not free_wallet)
            and (len(address) == 56)
            and (address[0] == "G")
        ):  # need activate
            await state.update_data(send_address=address)
            await state.set_state(state=None)
            await cmd_create_account(
                message.from_user.id, state, session, app_context=app_context
            )
        else:
            logger.error(
                f"StateSendFor: failed to find or activate wallet. Searched: {address}, free_wallet={free_wallet}"
            )
            msg = (
                my_gettext(message, "send_error2", app_context=app_context)
                + "\n"
                + my_gettext(message, "send_address", app_context=app_context)
            )
            await send_message(
                session,
                message,
                msg,
                reply_markup=get_kb_return(message, app_context=app_context),
                app_context=app_context,
            )


async def cmd_send_choose_token(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    app_context: AppContext,
):
    if message.from_user is None:
        return
    data = await state.get_data()
    address = data.get("send_address")

    # Refactored to use GetWalletBalance Use Case
    use_case = app_context.use_case_factory.create_get_wallet_balance(session)

    asset_list = await use_case.execute(user_id=message.from_user.id)
    sender_asset_list = await use_case.execute(
        user_id=message.from_user.id, public_key=address
    )

    if address == "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA":
        mtla_amount = 5
    else:
        mtlap_balance = [
            balance
            for balance in sender_asset_list
            if balance.asset_code == "MTLAP"
            and balance.asset_issuer
            == "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA"
        ]
        mtlac_balance = [
            balance
            for balance in sender_asset_list
            if balance.asset_code == "MTLAC"
            and balance.asset_issuer
            == "GCNVDZIHGX473FEI7IXCUAEXUJ4BGCKEMHF36VYP5EMS7PX2QBLAMTLA"
        ]
        mtlap_amount = get_first_balance_from_list(mtlap_balance) or 0.0
        mtlac_amount = get_first_balance_from_list(mtlac_balance) or 0.0

        mtla_amount = int(max(mtlap_amount, mtlac_amount))

    mtlap_stars = "⭐" * mtla_amount
    await state.update_data(mtlap_stars=mtlap_stars)

    if address is None:
        return
    link = "https://viewer.eurmtl.me/account/" + address

    link = f'<a href="{link}">{address}</a>{mtlap_stars}'
    msg = my_gettext(message, "choose_token", (link,), app_context=app_context)

    kb_tmp = []
    for token in asset_list:
        if my_float(token.balance) <= 0.0:
            continue
        for sender_token in sender_asset_list:
            if (
                token.asset_code == sender_token.asset_code
                and token.asset_issuer == sender_token.asset_issuer
            ):
                kb_tmp.append(
                    [
                        types.InlineKeyboardButton(
                            text=f"{token.asset_code} ({float2str(token.balance)})",
                            callback_data=SendAssetCallbackData(
                                answer=token.asset_code
                            ).pack(),
                        )
                    ]
                )
    kb_tmp.append(get_return_button(message, app_context=app_context))
    await send_message(
        session,
        message,
        msg,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb_tmp),
        need_new_msg=True,
        app_context=app_context,
    )
    await state.update_data(assets=jsonpickle.encode(asset_list))


@router.callback_query(SendAssetCallbackData.filter())
async def cb_send_choose_token(
    callback: types.CallbackQuery,
    callback_data: SendAssetCallbackData,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    answer = callback_data.answer
    data = await state.get_data()
    asset_list: List[Balance] = jsonpickle.decode(data["assets"])

    for asset in asset_list:
        if asset.asset_code == answer:
            if my_float(asset.balance) == 0.0:
                await callback.answer(
                    my_gettext(callback, "zero_sum", app_context=app_context),
                    show_alert=True,
                )
            else:
                msg = my_gettext(
                    callback,
                    "send_sum",
                    (asset.asset_code, asset.balance),
                    app_context=app_context,
                )

                # Get summ of tokens, blocked by Sell offers
                repo = app_context.repository_factory.get_wallet_repository(session)
                wallet = await repo.get_default_wallet(callback.from_user.id)
                if wallet is None:
                    return
                service = app_context.stellar_service
                offers = await service.get_selling_offers(wallet.public_key)

                blocked_token_sum = 0.0
                for offer in offers:
                    selling = offer.get("selling", {})
                    s_code = selling.get("asset_code")
                    s_issuer = selling.get("asset_issuer")
                    if s_code == asset.asset_code and s_issuer == asset.asset_issuer:
                        blocked_token_sum += float(offer.get("amount", 0))

                # If user has some assets that are blocked by offers, remind him\her about it.
                if blocked_token_sum > 0:
                    msg += "\n\n" + my_gettext(
                        callback,
                        "send_summ_blocked_by_offers",
                        (blocked_token_sum, asset.asset_code),
                        app_context=app_context,
                    )

                await state.update_data(
                    send_asset_code=asset.asset_code,
                    send_asset_issuer=asset.asset_issuer,
                    send_asset_max_sum=asset.balance,
                    send_asset_blocked_sum=blocked_token_sum,
                    msg=msg,
                )
                data = await state.get_data()  # Get updated data

                await state.set_state(StateSendToken.sending_sum)
                keyboard = get_kb_offers_cancel(
                    callback.from_user.id, data, app_context=app_context
                )
                await send_message(
                    session,
                    callback,
                    msg,
                    reply_markup=keyboard,
                    app_context=app_context,
                )
    return True


@router.callback_query(StateSendToken.sending_sum, F.data == "CancelOffers")
async def cq_send_cancel_offers_click(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    """
    Handle callback event 'CancelOffers_send' in state 'sending_sum'.
    Invert state of 'cancel offers' flag by clicking on button.
    """
    data = await state.get_data()
    data["cancel_offers"] = not data.get(
        "cancel_offers", False
    )  # Invert checkbox state
    await state.update_data(cancel_offers=data["cancel_offers"])

    # Update message with the same text and changed button checkbox state
    msg = data["msg"]
    keyboard = get_kb_offers_cancel(
        callback.from_user.id, data, app_context=app_context
    )
    await send_message(
        session, callback, msg, reply_markup=keyboard, app_context=app_context
    )


@router.message(StateSendToken.sending_sum)
async def cmd_send_get_sum(
    message: Message, state: FSMContext, session: AsyncSession, app_context: AppContext
):
    if message.from_user is None:
        return
    try:
        send_sum = my_float(message.text)
        # from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
        user_repo = app_context.repository_factory.get_user_repository(session)
        db_user = await user_repo.get_by_id(message.from_user.id)
        if db_user and db_user.can_5000 == 0 and send_sum > 5000:
            data = await state.get_data()
            msg0 = my_gettext(message, "need_update_limits", app_context=app_context)
            await send_message(
                session,
                message,
                msg0 + data["msg"],
                reply_markup=get_kb_return(message, app_context=app_context),
                app_context=app_context,
            )
            await message.delete()
            return

    except Exception:
        send_sum = 0.0

    data = await state.get_data()

    if send_sum > 0.0:
        await state.update_data(send_sum=send_sum)
        await state.set_state(None)

        await cmd_send_04(session, message, state, app_context=app_context)
        await message.delete()
    else:
        if message.from_user is None:
            return
        keyboard = get_kb_offers_cancel(
            message.from_user.id, data, app_context=app_context
        )
        await send_message(
            session,
            message,
            f"{my_gettext(message, 'bad_sum', app_context=app_context)}\n{data['msg']}",
            reply_markup=keyboard,
            app_context=app_context,
        )


async def cmd_send_04(
    session: AsyncSession,
    message: types.Message,
    state: FSMContext,
    need_new_msg=None,
    *,
    app_context: AppContext,
):
    data = await state.get_data()

    send_sum: float = data.get("send_sum", 0.0)
    send_address: str | None = data.get("send_address")
    send_memo: str | None = data.get("memo")
    federal_memo = data.get("federal_memo")
    send_asset_name = data["send_asset_code"]
    send_asset_issuer = data["send_asset_issuer"]
    cancel_offers = data.get("cancel_offers", False)
    mtlap_stars = data.get("mtlap_stars", "")

    if send_address is None:
        return
    if send_memo is None:
        send_memo_str = ""
    else:
        send_memo_str = send_memo

    # Add msg about cancelling offers to the confirmation request
    msg = my_gettext(
        message,
        "confirm_send",
        (
            float2str(send_sum),
            send_asset_name,
            send_address + " " + mtlap_stars,
            send_memo_str,
        ),
        app_context=app_context,
    )
    if cancel_offers:
        msg = msg + my_gettext(
            message,
            "confirm_cancel_offers",
            (send_asset_name,),
            app_context=app_context,
        )

    # Refactored to use Clean Architecture Use Case
    from core.domain.value_objects import Asset as DomainAsset

    use_case = app_context.use_case_factory.create_send_payment(session)

    if message.from_user is None:
        return
    result = await use_case.execute(
        user_id=message.from_user.id,
        destination_address=send_address,
        asset=DomainAsset(code=send_asset_name, issuer=send_asset_issuer),
        amount=send_sum,
        memo=send_memo,
        cancel_offers=cancel_offers,
    )

    if result.success:
        xdr = result.xdr
    else:
        # Fallback or error handling
        logger.error(f"SendPayment failed: {result.error_message}")
        await send_message(
            session,
            message,
            f"Error: {result.error_message}",
            reply_markup=get_kb_return(message, app_context=app_context),
            app_context=app_context,
        )
        return

    # xdr = await stellar_pay((await stellar_get_user_account(session, message.from_user.id)).account.account_id,
    #                         send_address,
    #                         Asset(send_asset_name, send_asset_issuer), send_sum, memo=send_memo,
    #                         cancel_offers=cancel_offers)

    await state.update_data(
        xdr=xdr,
        operation="send",
        msg=None,
        success_msg=my_gettext(
            message,
            "confirm_send_success",
            (
                float2str(send_sum),
                send_asset_name,
                send_address + " " + mtlap_stars,
                send_memo_str,
            ),
            app_context=app_context,
        ),
    )

    add_button_memo = federal_memo is None
    await send_message(
        session,
        message,
        msg,
        reply_markup=get_kb_yesno_send_xdr(
            message, add_button_memo=add_button_memo, app_context=app_context
        ),
        need_new_msg=need_new_msg,
        app_context=app_context,
    )


@router.callback_query(F.data == "Memo")
async def cmd_get_memo(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    msg = my_gettext(callback, "send_memo", app_context=app_context)
    await state.set_state(StateSendToken.sending_memo)
    await send_message(
        session,
        callback,
        msg,
        reply_markup=get_kb_return(callback, app_context=app_context),
        app_context=app_context,
    )


@router.message(StateSendToken.sending_memo)
async def cmd_send_memo(
    message: Message, state: FSMContext, session: AsyncSession, app_context: AppContext
):
    if message.text is None:
        return
    send_memo = cut_text_to_28_bytes(message.text)

    if len(send_memo) > 0:
        await state.update_data(memo=send_memo)
    await cmd_send_04(
        session, message, state, need_new_msg=True, app_context=app_context
    )


async def cmd_create_account(
    user_id: int, state: FSMContext, session: AsyncSession, *, app_context: AppContext
):
    data = await state.get_data()

    send_sum = data.get("activate_sum", 5)
    send_address = data.get("send_address", "None 0_0")
    msg = my_gettext(
        user_id, "confirm_activate", (send_address, send_sum), app_context=app_context
    )

    # Refactored to use SendPayment Use Case with create_account=True
    from core.domain.value_objects import Asset as DomainAsset
    from loguru import logger

    use_case = app_context.use_case_factory.create_send_payment(session)

    result = await use_case.execute(
        user_id=user_id,
        destination_address=send_address,
        asset=DomainAsset(code="XLM"),
        amount=float(send_sum),
        create_account=True,
    )

    if result.success:
        xdr = result.xdr
    else:
        logger.error(f"cmd_create_account failed: {result.error_message}")
        await send_message(
            session,
            user_id,
            f"Error: {result.error_message}",
            reply_markup=get_kb_return(user_id, app_context=app_context),
            app_context=app_context,
        )
        return

    await state.update_data(
        xdr=xdr, send_asset_code="XLM", send_asset_issuer=None, send_sum=send_sum
    )

    kb = get_kb_yesno_send_xdr(user_id, app_context=app_context)
    kb.inline_keyboard.insert(
        1, [types.InlineKeyboardButton(text="Send 15 xlm", callback_data="Send15xlm")]
    )
    await send_message(
        session,
        user_id,
        msg,
        reply_markup=kb,
        need_new_msg=True,
        app_context=app_context,
    )


@router.callback_query(F.data == "Send15xlm")
async def cmd_send_15_xlm(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    await state.update_data(activate_sum=15)
    await cmd_create_account(
        callback.from_user.id, state, session, app_context=app_context
    )


@router.message(StateSendToken.sending_for, F.photo)
@router.message(F.photo)
async def handle_docs_photo(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None:
        return
    logger.info(f"{message.from_user.id}")
    if message.photo:
        await message.reply("is being recognized")
        bot = app_context.bot
        await bot.download(
            message.photo[-1], destination=f"qr/{message.from_user.id}.jpg"
        )

        qr_data = decode_qr_code(f"qr/{message.from_user.id}.jpg")
        # decode(Image.open(f"qr/{message.from_user.id}.jpg"))
        if qr_data:
            logger.info(qr_data)

            if is_valid_stellar_address(qr_data):
                await state.update_data(qr=qr_data, last_message_id=0)
                await message.reply(
                    f"QR code: <code>{qr_data}</code>\npreparations are in progress..."
                )
                await cmd_send_for(message, state, session, app_context=app_context)
            elif len(qr_data) > 56 and qr_data.startswith("web+stellar:pay"):
                # Parse payment URI
                payment_data = await parse_pay_stellar_uri(qr_data)

                # Update state with payment data
                await state.update_data(
                    send_sum=payment_data["amount"],
                    send_address=payment_data["destination"],
                    memo=payment_data["memo"],
                    send_asset_code=payment_data["asset_code"],
                    send_asset_issuer=payment_data["asset_issuer"],
                    last_message_id=0,
                )

                await cmd_send_04(session, message, state, app_context=app_context)
            elif len(qr_data) > 56 and qr_data.startswith("web+stellar:tx"):
                await clear_state(state)
                # Process transaction URI with Clean Architecture Use Case
                use_case = app_context.use_case_factory.create_process_stellar_uri(
                    session
                )

                result = await use_case.execute(qr_data, message.from_user.id)

                if not result.success:
                    await send_message(
                        session,
                        message.from_user.id,
                        f"Error: {result.error_message}",
                        app_context=app_context,
                    )
                    return

                # Update state with transaction data
                await state.update_data(
                    last_message_id=0,
                    callback_url=result.callback_url,
                    return_url=result.return_url,
                )

                # Process XDR
                await cmd_check_xdr(
                    session=session,
                    check_xdr=result.xdr,
                    user_id=message.from_user.id,
                    state=state,
                    app_context=app_context,
                )

            elif qr_data.startswith("wc:"):
                await handle_wc_uri(
                    qr_data,
                    message.from_user.id,
                    session,
                    state,
                    app_context=app_context,
                )
                await message.delete()

            else:
                await message.reply("Bad QR code =(")
        else:
            await message.reply("Bad QR code =(")


@router.inline_query(F.chat_type == "sender")
async def cmd_inline_query(
    inline_query: types.InlineQuery, session: AsyncSession, app_context: AppContext
):
    if inline_query.chat_type != "sender" or inline_query.from_user is None:
        await inline_query.answer([], is_personal=True, cache_time=100)
        return

    results: list[types.InlineQueryResult] = []
    seen_ids = set()  # Для отслеживания уникальных идентификаторов

    # Query from the address book
    # from infrastructure.persistence.sqlalchemy_addressbook_repository import SqlAlchemyAddressBookRepository
    addressbook_repo = app_context.repository_factory.get_addressbook_repository(
        session
    )
    book_entries = await addressbook_repo.get_all(inline_query.from_user.id)
    data = [(entry.address, entry.name) for entry in book_entries]

    # Query from the wallets
    # from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallets = await wallet_repo.get_all_active(inline_query.from_user.id)
    for wallet in wallets:
        simple_account = wallet.public_key[:4] + ".." + wallet.public_key[-4:]
        data.append((wallet.public_key, simple_account))

    if len(inline_query.query) > 2:
        for record in data:
            if (record[0] + record[1]).upper().find(inline_query.query.upper()) != -1:
                if record[0] not in seen_ids:
                    seen_ids.add(record[0])
                    results.append(
                        types.InlineQueryResultArticle(
                            id=record[0],
                            title=record[1],
                            input_message_content=types.InputTextMessageContent(
                                message_text=record[0]
                            ),
                        )
                    )

        # Query from users
        # from infrastructure.persistence.sqlalchemy_user_repository import SqlAlchemyUserRepository
        user_repo = app_context.repository_factory.get_user_repository(session)
        usernames = await user_repo.search_by_username(inline_query.query)
        for username in usernames:
            user = f"@{username}"
            if user not in seen_ids:
                seen_ids.add(user)
                results.append(
                    types.InlineQueryResultArticle(
                        id=user,
                        title=user,
                        input_message_content=types.InputTextMessageContent(
                            message_text=user
                        ),
                    )
                )

        await inline_query.answer(results[:49], is_personal=True)  # type: ignore[arg-type]

    else:
        for record in data:
            if record[0] not in seen_ids:
                seen_ids.add(record[0])
                results.append(
                    types.InlineQueryResultArticle(
                        id=record[0],
                        title=record[1],
                        input_message_content=types.InputTextMessageContent(
                            message_text=record[0]
                        ),
                    )
                )

        await inline_query.answer(results[:49], is_personal=True)  # type: ignore[arg-type]
