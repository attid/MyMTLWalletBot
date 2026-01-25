from contextlib import suppress

import jsonpickle  # type: ignore
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from keyboards.common_keyboards import get_kb_return, get_return_button
from routers.sign import cmd_ask_pin, PinState
from routers.start_msg import cmd_show_balance, cmd_info_message
from infrastructure.utils.telegram_utils import send_message, my_gettext
from other.locks import new_wallet_lock

from infrastructure.services.app_context import AppContext


class StateAddWallet(StatesGroup):
    sending_private = State()
    sending_public = State()


router = Router()
router.message.filter(F.chat.type == "private")


@router.callback_query(F.data == "AddNew")
async def cmd_add_new(
    callback: types.CallbackQuery, session: AsyncSession, app_context: AppContext
):
    buttons = [
        [
            types.InlineKeyboardButton(
                text=my_gettext(callback, "kb_have_key", app_context=app_context),
                callback_data="AddWalletHaveKey",
            )
        ],
        [
            types.InlineKeyboardButton(
                text=my_gettext(callback, "kb_get_free", app_context=app_context),
                callback_data="AddWalletNewKey",
            )
        ],
        [
            types.InlineKeyboardButton(
                text=my_gettext(callback, "kb_read_only", app_context=app_context),
                callback_data="AddWalletReadOnly",
            )
        ],
        [
            types.InlineKeyboardButton(
                text="Create new TON wallet", callback_data="AddTonWallet"
            )
        ],
        get_return_button(callback, app_context=app_context),
    ]
    msg = my_gettext(callback, "create_msg", app_context=app_context)
    await send_message(
        session,
        callback,
        msg,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        app_context=app_context,
    )


@router.callback_query(F.data == "AddWalletHaveKey")
async def cq_add_have_key(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    msg = my_gettext(callback, "send_key", app_context=app_context)
    await state.update_data(msg=msg)
    await state.set_state(StateAddWallet.sending_private)
    await send_message(
        session,
        callback,
        msg,
        reply_markup=get_kb_return(callback, app_context=app_context),
        app_context=app_context,
    )


@router.message(StateAddWallet.sending_private)
async def cmd_sending_private(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None or message.text is None:
        return
    try:
        args = message.text.split()
        secret_key = args[0]
        kp = app_context.stellar_service.get_keypair_from_secret(secret_key)
        public_key = kp.public_key

        assert app_context.use_case_factory is not None, (
            "use_case_factory must be initialized"
        )
        add_wallet = app_context.use_case_factory.create_add_wallet(session)

        assert app_context.encryption_service is not None, (
            "encryption_service must be initialized"
        )
        encrypted_secret = app_context.encryption_service.encrypt(
            secret_key, str(message.from_user.id)
        )

        await add_wallet.execute(
            user_id=message.from_user.id,
            public_key=public_key,
            secret_key=encrypted_secret,
            is_free=False,
            is_default=False,
        )
        await session.commit()

        # Subscribe to notifications
        if app_context.notification_service:
            await app_context.notification_service.subscribe(public_key)

        await state.update_data(public_key=public_key)
        await state.set_state(None)
        await cmd_show_add_wallet_choose_pin(
            session,
            message.chat.id,
            state,
            my_gettext(message, "for_address", (public_key,), app_context=app_context),
            app_context=app_context,
        )
        await message.delete()
    except Exception as ex:
        logger.info(ex)
        data = await state.get_data()
        await send_message(
            session,
            message,
            my_gettext(message, "bad_key", app_context=app_context)
            + "\n"
            + data["msg"],
            reply_markup=get_kb_return(message, app_context=app_context),
            app_context=app_context,
        )


@router.callback_query(F.data == "AddWalletNewKey")
async def cq_add_new_key(
    callback: types.CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    app_context: AppContext,
):
    if (
        callback.from_user is None
        or callback.message is None
        or callback.message.chat is None
    ):
        return
    assert app_context.repository_factory is not None, (
        "repository_factory must be initialized"
    )
    assert app_context.use_case_factory is not None, (
        "use_case_factory must be initialized"
    )
    assert app_context.encryption_service is not None, (
        "encryption_service must be initialized"
    )
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    add_wallet = app_context.use_case_factory.create_add_wallet(session)

    try:
        count = await wallet_repo.count_free_wallets(callback.from_user.id)
        if count > 2:
            await callback.answer(
                my_gettext(
                    callback.message.chat.id, "max_wallets", app_context=app_context
                ),
                show_alert=True,
            )
            return

        msg = my_gettext(callback, "try_send", app_context=app_context)
        waiting_count = new_wallet_lock.waiting_count()
        if waiting_count > 0:
            await cmd_info_message(
                session,
                callback.message.chat.id,
                f"Please wait, your position in the queue is {waiting_count}.",
                app_context=app_context,
            )

        async with new_wallet_lock:
            mnemonic = app_context.stellar_service.generate_mnemonic()
            kp = app_context.stellar_service.get_keypair_from_mnemonic(mnemonic)

            encrypted_secret = app_context.encryption_service.encrypt(
                kp.secret, str(callback.from_user.id)
            )
            encrypted_seed = app_context.encryption_service.encrypt(mnemonic, kp.secret)

            await add_wallet.execute(
                user_id=callback.from_user.id,
                public_key=kp.public_key,
                secret_key=encrypted_secret,
                seed_key=encrypted_seed,
                is_free=True,
                is_default=False,
            )
            await session.commit()

            await cmd_info_message(
                session, callback.message.chat.id, msg, app_context=app_context
            )

            # Subscribe to notifications
            if app_context.notification_service:
                await app_context.notification_service.subscribe(kp.public_key)

            service = app_context.stellar_service
            master_wallet = await wallet_repo.get_default_wallet(0)
            if not master_wallet:
                logger.error("No master wallet found!")
                await send_message(
                    session,
                    callback,
                    "Error: System wallet missing",
                    app_context=app_context,
                )
                return

            assert master_wallet.secret_key is not None, (
                "master_wallet.secret_key must not be None"
            )
            master_secret = app_context.encryption_service.decrypt(
                master_wallet.secret_key, "0"
            )
            assert master_secret is not None, "master_secret must not be None"

            xdr = await service.build_payment_transaction(
                source_account_id=master_wallet.public_key,
                destination_account_id=kp.public_key,
                asset_code="XLM",
                asset_issuer=None,
                amount="5",
                create_account=True,
            )
            signed_xdr = await service.sign_transaction(xdr, master_secret)
            await service.submit_transaction(signed_xdr)

            from core.constants import (
                MTL_ASSET,
                EURMTL_ASSET,
                SATSMTL_ASSET,
                USDM_ASSET,
            )

            for asset in [MTL_ASSET, EURMTL_ASSET, SATSMTL_ASSET, USDM_ASSET]:
                trust_xdr = await service.build_change_trust_transaction(
                    source_account_id=kp.public_key,
                    asset_code=asset.code,
                    asset_issuer=asset.issuer,  # type: ignore[arg-type]
                )
                signed_trust = await service.sign_transaction(trust_xdr, kp.secret)
                await service.submit_transaction(signed_trust)

        await cmd_info_message(
            session,
            callback,
            my_gettext(callback, "send_good", app_context=app_context),
            app_context=app_context,
        )
        with suppress(TelegramBadRequest):
            await callback.answer()
        data = await state.get_data()
        fsm_after_send = data.get("fsm_after_send")
        if fsm_after_send:
            fsm_after_send_func = jsonpickle.loads(fsm_after_send)
            await fsm_after_send_func(
                session, callback.from_user.id, state, app_context=app_context
            )

    except Exception as e:
        logger.error(f"Error creating wallet: {e}")
        await callback.answer(f"Error: {e}", show_alert=True)


async def cmd_show_add_wallet_choose_pin(
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    msg="",
    *,
    app_context: AppContext,
):
    buttons = [
        [
            types.InlineKeyboardButton(
                text=my_gettext(user_id, "kb_pin", app_context=app_context),
                callback_data="PIN",
            )
        ],
        [
            types.InlineKeyboardButton(
                text=my_gettext(user_id, "kb_password", app_context=app_context),
                callback_data="Password",
            )
        ],
        [
            types.InlineKeyboardButton(
                text=my_gettext(user_id, "kb_no_password", app_context=app_context),
                callback_data="NoPassword",
            ),
        ],
    ]

    msg = msg + my_gettext(user_id, "choose_protect", app_context=app_context)
    await send_message(
        session,
        user_id,
        msg,
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
        app_context=app_context,
    )


@router.callback_query(F.data == "AddWalletReadOnly")
async def cq_add_read_only(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    msg = my_gettext(callback, "add_read_only", app_context=app_context)
    await state.update_data(msg=msg)
    await state.set_state(StateAddWallet.sending_public)
    await send_message(
        session,
        callback,
        msg,
        reply_markup=get_kb_return(callback, app_context=app_context),
        app_context=app_context,
    )


@router.message(StateAddWallet.sending_public)
async def cmd_sending_public(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    if message.from_user is None or message.text is None:
        return
    try:
        public_key = message.text
        assert app_context.use_case_factory is not None, (
            "use_case_factory must be initialized"
        )
        add_wallet = app_context.use_case_factory.create_add_wallet(session)

        await add_wallet.execute(
            user_id=message.from_user.id,
            public_key=public_key,
            secret_key=public_key,
            is_free=False,
            is_read_only=True,
            is_default=False,
        )
        await session.commit()

        await state.update_data(public_key=public_key)
        await state.set_state(None)

        await cmd_show_balance(
            session, message.from_user.id, state, app_context=app_context
        )
        await message.delete()
    except Exception as ex:
        logger.info(ex)
        data = await state.get_data()
        await send_message(
            session,
            message,
            my_gettext(message, "bad_key", app_context=app_context)
            + "\n"
            + data["msg"],
            reply_markup=get_kb_return(message, app_context=app_context),
            app_context=app_context,
        )


@router.callback_query(F.data == "PIN")
async def cq_add_read_only_pin(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    assert callback.message is not None and callback.message.chat is not None, (
        "callback.message and chat must not be None"
    )
    await state.set_state(PinState.set_pin)
    await state.update_data(pin_type=1)
    await cmd_ask_pin(session, callback.message.chat.id, state, app_context=app_context)


@router.callback_query(F.data == "Password")
async def cq_add_password(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    await state.update_data(pin_type=2)
    await state.set_state(PinState.ask_password_set)
    await send_message(
        session,
        callback,
        my_gettext(callback, "send_password", app_context=app_context),
        reply_markup=get_kb_return(callback, app_context=app_context),
        app_context=app_context,
    )


@router.callback_query(F.data == "NoPassword")
async def cq_add_read_only_no_password(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    await state.update_data(pin_type=0)
    await cmd_show_balance(
        session, callback.from_user.id, state, app_context=app_context
    )


@router.callback_query(F.data == "AddTonWallet")
async def cq_add_ton(
    callback: types.CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    app_context: AppContext,
):
    if (
        callback.from_user is None
        or callback.message is None
        or callback.message.chat is None
    ):
        return
    try:
        assert app_context.use_case_factory is not None, (
            "use_case_factory must be initialized"
        )
        assert app_context.repository_factory is not None, (
            "repository_factory must be initialized"
        )
        add_wallet = app_context.use_case_factory.create_add_wallet(session)
        wallet_repo = app_context.repository_factory.get_wallet_repository(session)

        count = await wallet_repo.count_free_wallets(callback.from_user.id)
        if count > 2:
            await callback.answer(
                my_gettext(
                    callback.message.chat.id, "max_wallets", app_context=app_context
                ),
                show_alert=True,
            )
            return

        ton_service = app_context.ton_service
        if ton_service is None:
            return
        wallet_obj, mnemonic_list = ton_service.generate_wallet()
        public_key = wallet_obj.address.to_str(is_bounceable=False)
        seed_key = mnemonic_list
        seed_str: str
        if isinstance(seed_key, list):
            seed_str = " ".join(seed_key)
        else:
            seed_str = seed_key

        await add_wallet.execute(
            user_id=callback.from_user.id,
            public_key=public_key,
            secret_key="TON",
            seed_key=seed_str,
            is_free=True,
            is_default=False,
        )
        await session.commit()

        await cmd_info_message(
            session,
            callback,
            my_gettext(callback, "send_good", app_context=app_context),
            app_context=app_context,
        )
    except Exception as e:
        logger.error(f"Error adding TON wallet: {e}")
        await callback.answer(f"Error: {e}", show_alert=True)
