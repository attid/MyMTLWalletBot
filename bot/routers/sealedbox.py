"""Telegram flow for Stellar sealed-box file encryption."""

from __future__ import annotations

import base64
from io import BytesIO
import re

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from stellar_sdk import StrKey

from infrastructure.services.app_context import AppContext
from infrastructure.services.localization_service import LocalizationService
from infrastructure.services.stellar_sealedbox_service import (
    MAX_BASE64_CIPHERTEXT_BYTES,
    MAX_PLAINTEXT_BYTES,
    SealedBoxDecryptionError,
    SealedBoxRateLimitError,
    SealedBoxSizeError,
)
from infrastructure.utils.telegram_utils import (
    clear_last_message_id,
    clear_state,
    send_message,
    send_ui_document,
)
from keyboards.common_keyboards import get_kb_return
from middleware.notification_activity import complete_notification_flow
from other.lang_tools import my_gettext


router = Router()
router.message.filter(F.chat.type == "private")

DOCUMENT_CAPTION_LIMIT = 1024


class SealedBoxState(StatesGroup):
    recipient = State()
    encrypt_content = State()
    decrypt_file = State()
    decrypt_auth = State()


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class _LimitedBytesIO(BytesIO):
    def __init__(self, max_bytes: int) -> None:
        super().__init__()
        self._max_bytes = max_bytes

    def write(self, data: bytes) -> int:
        if self.tell() + len(data) > self._max_bytes:
            raise ValueError("download exceeds the allowed size")
        return super().write(data)


def _button(text: str, callback_data: str) -> list[types.InlineKeyboardButton]:
    return [types.InlineKeyboardButton(text=text, callback_data=callback_data)]


def _navigation(
    user_id: int, back_target: str, app_context: AppContext
) -> list[list[types.InlineKeyboardButton]]:
    return [
        _button(
            my_gettext(user_id, "kb_back", app_context=app_context),
            f"SealedBoxBack:{back_target}",
        ),
        _button(
            my_gettext(user_id, "kb_return", app_context=app_context),
            "Return",
        ),
    ]


async def _show_menu(
    session: AsyncSession, user_id: int, app_context: AppContext
) -> None:
    buttons = [
        _button(
            my_gettext(user_id, "sealedbox_encrypt", app_context=app_context),
            "SealedBoxEncrypt",
        ),
        _button(
            my_gettext(user_id, "sealedbox_decrypt", app_context=app_context),
            "SealedBoxDecrypt",
        ),
        *_navigation(user_id, "settings", app_context),
    ]
    await send_message(
        session,
        user_id,
        my_gettext(user_id, "sealedbox_menu", app_context=app_context),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        app_context=app_context,
    )


@router.callback_query(F.data == "SealedBoxMenu")
async def open_sealedbox_menu(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    user_id = callback.from_user.id
    await clear_state(state)
    await state.update_data(user_id=user_id)
    await _show_menu(session, user_id, app_context)
    await callback.answer()


@router.message(Command(commands=["crypto"]))
async def open_sealedbox_menu_command(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    await message.delete()
    await clear_state(state)
    await clear_last_message_id(user_id, app_context=app_context)
    await state.update_data(user_id=user_id)
    await _show_menu(session, user_id, app_context)


@router.callback_query(F.data == "SealedBoxBack:menu")
async def back_to_sealedbox_menu(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    await clear_state(state)
    await _show_menu(session, callback.from_user.id, app_context)
    await callback.answer()


@router.callback_query(F.data == "SealedBoxBack:settings")
async def back_to_settings(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
    l10n: LocalizationService,
) -> None:
    from routers.wallet_setting import cmd_wallet_setting

    await clear_state(state)
    await cmd_wallet_setting(callback, state, session, app_context, l10n)
    await callback.answer()


@router.callback_query(F.data == "SealedBoxEncrypt")
async def start_encrypt(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    await _show_recipient_selection(session, callback.from_user.id, state, app_context)
    await callback.answer()


async def _show_recipient_selection(
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    app_context: AppContext,
) -> None:
    buttons = [
        [
            types.InlineKeyboardButton(
                text=my_gettext(user_id, "kb_choose", app_context=app_context),
                switch_inline_query_current_chat="",
            )
        ]
    ]
    buttons.extend(_navigation(user_id, "menu", app_context))
    await state.set_state(SealedBoxState.recipient)
    await send_message(
        session,
        user_id,
        my_gettext(user_id, "sealedbox_choose_recipient", app_context=app_context),
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
        app_context=app_context,
    )


@router.callback_query(F.data == "SealedBoxBack:recipient")
async def back_to_recipient_selection(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    await _show_recipient_selection(session, callback.from_user.id, state, app_context)
    await callback.answer()


@router.message(SealedBoxState.recipient)
async def receive_recipient(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    if message.from_user is None:
        return
    recipient = message.text.strip().upper() if message.text else ""
    await message.delete()
    if not StrKey.is_valid_ed25519_public_key(recipient):
        await _show_error(
            session,
            message.from_user.id,
            "sealedbox_bad_address",
            "menu",
            app_context,
        )
        return
    await _accept_recipient(
        session, message.from_user.id, recipient, state, app_context=app_context
    )


async def _accept_recipient(
    session: AsyncSession,
    user_id: int,
    recipient: str,
    state: FSMContext,
    *,
    app_context: AppContext,
) -> None:
    await state.update_data(sealedbox_recipient=recipient)
    await state.set_state(SealedBoxState.encrypt_content)
    await send_message(
        session,
        user_id,
        my_gettext(
            user_id,
            "sealedbox_send_content",
            (_short_address(recipient),),
            app_context=app_context,
        ),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=_navigation(user_id, "recipient", app_context)
        ),
        app_context=app_context,
    )


@router.message(SealedBoxState.encrypt_content)
async def receive_encrypt_content(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    if message.document:
        if (message.document.file_size or 0) > MAX_PLAINTEXT_BYTES:
            await message.delete()
            await _show_error(
                session,
                user_id,
                "sealedbox_file_too_large",
                "recipient",
                app_context,
            )
            return
        try:
            try:
                plaintext = await _download_document(
                    message, app_context, MAX_PLAINTEXT_BYTES
                )
            finally:
                await message.delete()
        except ValueError:
            await _show_error(
                session,
                user_id,
                "sealedbox_file_too_large",
                "recipient",
                app_context,
            )
            return
        filename = _safe_filename(message.document.file_name, "file.bin")
    elif message.text:
        plaintext = message.text.encode("utf-8")
        filename = "message.txt"
        await message.delete()
    else:
        await message.delete()
        await _show_error(
            session, user_id, "sealedbox_send_as_file", "recipient", app_context
        )
        return
    if not plaintext:
        await _show_error(
            session, user_id, "sealedbox_empty_content", "recipient", app_context
        )
        return

    recipient = str((await state.get_data()).get("sealedbox_recipient", ""))
    service = app_context.stellar_sealedbox_service
    if service is None:
        raise RuntimeError("stellar sealed-box service is not configured")
    try:
        ciphertext = await service.encrypt(user_id, recipient, plaintext)
    except SealedBoxRateLimitError:
        await _show_error(
            session, user_id, "sealedbox_rate_limited", "recipient", app_context
        )
        return
    except SealedBoxSizeError:
        await _show_error(
            session,
            user_id,
            "sealedbox_file_too_large",
            "recipient",
            app_context,
        )
        return

    await _send_result_document(
        app_context,
        user_id,
        BufferedInputFile(ciphertext, filename=f"{filename}.ssb"),
        caption=_build_encryption_caption(user_id, recipient, ciphertext, app_context),
    )
    logger.info(
        "sealed-box operation completed: user_id={} operation=encrypt size={} result=success",
        user_id,
        len(plaintext),
    )
    await _complete_flow(user_id, state, app_context)


@router.callback_query(F.data == "SealedBoxDecrypt")
async def start_decrypt(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    user_id = callback.from_user.id
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await wallet_repo.get_default_wallet(user_id)
    if wallet is None:
        await callback.answer(
            my_gettext(user_id, "sealedbox_wallet_missing", app_context=app_context),
            show_alert=True,
        )
        return
    await state.update_data(
        sealedbox_wallet_address=wallet.public_key,
        sealedbox_pin_type=wallet.use_pin,
    )
    await _show_decrypt_file(session, user_id, state, app_context)
    await callback.answer()


async def _show_decrypt_file(
    session: AsyncSession,
    user_id: int,
    state: FSMContext,
    app_context: AppContext,
) -> None:
    await state.set_state(SealedBoxState.decrypt_file)
    await send_message(
        session,
        user_id,
        my_gettext(user_id, "sealedbox_send_file", app_context=app_context),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=_navigation(user_id, "menu", app_context)
        ),
        app_context=app_context,
    )


@router.callback_query(F.data == "SealedBoxBack:decrypt_file")
async def back_to_decrypt_file(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    from other.faststream_tools import clear_pending_sealedbox

    data = await state.get_data()
    data.pop("sealedbox_pending_ciphertext", None)
    data.pop("sealedbox_pending_filename", None)
    await state.set_data(data)
    await clear_pending_sealedbox(callback.from_user.id)
    await _show_decrypt_file(session, callback.from_user.id, state, app_context)
    await callback.answer()


@router.message(SealedBoxState.decrypt_file)
async def receive_decrypt_file(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    if message.document is not None:
        if (message.document.file_size or 0) > MAX_BASE64_CIPHERTEXT_BYTES:
            await message.delete()
            await _show_error(
                session, user_id, "sealedbox_file_too_large", "menu", app_context
            )
            return
        try:
            try:
                payload = await _download_document(
                    message, app_context, MAX_BASE64_CIPHERTEXT_BYTES
                )
            finally:
                await message.delete()
        except ValueError:
            await _show_error(
                session, user_id, "sealedbox_file_too_large", "menu", app_context
            )
            return
        filename = _requested_output_filename(message.document.file_name)
    elif message.text is not None:
        encoded = "".join(message.text.split())
        await message.delete()
        try:
            if len(encoded) > MAX_BASE64_CIPHERTEXT_BYTES:
                raise ValueError("ciphertext is too large")
            payload = base64.b64decode(encoded, validate=True)
            if not payload:
                raise ValueError("ciphertext is empty")
        except (ValueError, base64.binascii.Error):
            await _show_error(
                session, user_id, "sealedbox_decrypt_failed", "menu", app_context
            )
            return
        filename = ""
    else:
        await message.delete()
        await _show_error(
            session, user_id, "sealedbox_send_as_file", "menu", app_context
        )
        return
    data = await state.get_data()
    pin_type = int(data.get("sealedbox_pin_type", 0))
    if pin_type == 10:
        await _start_webapp_decrypt(
            session, user_id, payload, filename, state, app_context
        )
        return
    if pin_type in (1, 2):
        await state.update_data(
            sealedbox_pending_ciphertext=base64.b64encode(payload).decode("ascii"),
            sealedbox_pending_filename=filename,
        )
        await state.set_state(SealedBoxState.decrypt_auth)
        await send_message(
            session,
            user_id,
            my_gettext(user_id, "sealedbox_enter_password", app_context=app_context),
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=_navigation(user_id, "decrypt_file", app_context)
            ),
            app_context=app_context,
        )
        return
    await _decrypt_server(
        session,
        user_id,
        payload,
        filename,
        str(user_id),
        "menu",
        state,
        app_context,
    )


@router.message(SealedBoxState.decrypt_auth)
async def receive_decrypt_password(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    password = message.text.upper() if message.text else ""
    await message.delete()
    if message.text is None:
        await _show_error(session, user_id, "bad_password", "decrypt_file", app_context)
        return
    data = await state.get_data()
    encoded = data.get("sealedbox_pending_ciphertext")
    if not encoded:
        await _show_error(
            session, user_id, "sealedbox_file_expired", "menu", app_context
        )
        return
    await _decrypt_server(
        session,
        user_id,
        base64.b64decode(encoded, validate=True),
        str(data.get("sealedbox_pending_filename", "")),
        password,
        "decrypt_file",
        state,
        app_context,
    )


async def _decrypt_server(
    session: AsyncSession,
    user_id: int,
    payload: bytes,
    filename: str,
    pin: str,
    back_target: str,
    state: FSMContext,
    app_context: AppContext,
) -> None:
    get_secrets = app_context.use_case_factory.create_get_wallet_secrets(session)
    secrets = await get_secrets.execute(user_id, pin)
    if secrets is None:
        await _show_error(session, user_id, "bad_password", back_target, app_context)
        return
    service = app_context.stellar_sealedbox_service
    if service is None:
        raise RuntimeError("stellar sealed-box service is not configured")
    try:
        plaintext = await service.decrypt(user_id, secrets.secret_key, payload)
    except SealedBoxRateLimitError:
        await _show_error(
            session, user_id, "sealedbox_rate_limited", back_target, app_context
        )
        return
    except (SealedBoxDecryptionError, SealedBoxSizeError):
        logger.info(
            "sealed-box operation completed: user_id={} operation=decrypt size={} result=failed",
            user_id,
            len(payload),
        )
        await _show_error(
            session, user_id, "sealedbox_decrypt_failed", back_target, app_context
        )
        return

    await _send_result_document(
        app_context,
        user_id,
        BufferedInputFile(
            plaintext, filename=_resolve_output_filename(filename, plaintext)
        ),
    )
    logger.info(
        "sealed-box operation completed: user_id={} operation=decrypt size={} result=success",
        user_id,
        len(payload),
    )
    await _complete_flow(user_id, state, app_context)


async def _send_result_document(
    app_context: AppContext,
    user_id: int,
    document: BufferedInputFile,
    *,
    caption: str | None = None,
) -> None:
    await send_ui_document(
        user_id,
        document,
        caption=caption,
        reply_markup=get_kb_return(user_id, app_context=app_context),
        app_context=app_context,
    )


async def _start_webapp_decrypt(
    session: AsyncSession,
    user_id: int,
    payload: bytes,
    filename: str,
    state: FSMContext,
    app_context: AppContext,
) -> None:
    from keyboards.webapp import webapp_sealedbox_keyboard
    from other.faststream_tools import publish_pending_sealedbox

    data = await state.get_data()
    token = await publish_pending_sealedbox(
        user_id=user_id,
        wallet_address=str(data.get("sealedbox_wallet_address", "")),
        ciphertext=payload,
        output_filename=filename,
    )
    await send_message(
        session,
        user_id,
        my_gettext(user_id, "sealedbox_webapp_prompt", app_context=app_context),
        reply_markup=webapp_sealedbox_keyboard(token, user_id, app_context),
        app_context=app_context,
    )


async def _download_document(
    message: types.Message, app_context: AppContext, max_bytes: int
) -> bytes:
    assert message.document is not None
    destination = _LimitedBytesIO(max_bytes)
    await app_context.bot.download(message.document, destination=destination)
    return destination.getvalue()


async def _show_error(
    session: AsyncSession,
    user_id: int,
    key: str,
    back_target: str,
    app_context: AppContext,
) -> None:
    await send_message(
        session,
        user_id,
        my_gettext(user_id, key, app_context=app_context),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=_navigation(user_id, back_target, app_context)
        ),
        app_context=app_context,
    )


async def _complete_flow(
    user_id: int, state: FSMContext, app_context: AppContext
) -> None:
    await clear_state(state)
    await complete_notification_flow(app_context, user_id)


def _short_address(address: str) -> str:
    return f"{address[:4]}…{address[-4:]}" if len(address) > 10 else address


def _build_encryption_caption(
    user_id: int,
    recipient: str,
    ciphertext: bytes,
    app_context: AppContext,
) -> str:
    address_caption = my_gettext(
        user_id,
        "sealedbox_encrypted_for",
        (_short_address(recipient),),
        app_context=app_context,
    )
    encoded = base64.b64encode(ciphertext).decode("ascii")
    if len(address_caption) + 2 + len(encoded) <= DOCUMENT_CAPTION_LIMIT:
        return f"{address_caption}\n\n<code>{encoded}</code>"
    return address_caption


def _safe_filename(filename: str | None, fallback: str) -> str:
    candidate = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    candidate = _CONTROL_CHARS.sub("", candidate).strip(" .")
    return (candidate or fallback)[:180]


def _requested_output_filename(filename: str | None) -> str:
    candidate = _safe_filename(filename, "sealedbox.ssb")
    if candidate.lower().endswith(".ssb") and candidate.lower() != "sealedbox.ssb":
        return candidate[:-4] or "sealedbox-output.bin"
    return ""


def _resolve_output_filename(requested: str, plaintext: bytes) -> str:
    if requested:
        return requested
    return (
        "sealedbox-output.txt"
        if _looks_like_utf8(plaintext)
        else "sealedbox-output.bin"
    )


def _looks_like_utf8(payload: bytes) -> bool:
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
