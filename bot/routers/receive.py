from contextlib import suppress
from io import BytesIO
import math

import qrcode
from PIL import ImageDraw, Image, ImageFont
from aiogram import Router, types, F
from aiogram.types import BufferedInputFile, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import EURMTL_ASSET, XLM_ASSET
from core.domain.value_objects import Balance
from infrastructure.services.app_context import AppContext
from infrastructure.services.receive_history_store import (
    HistoryAmount,
    ReceiveHistoryStore,
)
from infrastructure.utils.common_utils import float2str, get_user_id
from infrastructure.utils.stellar_utils import my_float
from infrastructure.utils.telegram_utils import (
    clear_last_message_id,
    clear_state,
    my_gettext,
    send_message,
)
from keyboards.common_keyboards import get_kb_return, get_return_button
from other import faststream_tools

router = Router()
router.message.filter(F.chat.type == "private")


class ReceiveInvoiceStates(StatesGroup):
    entering_amount = State()


RECEIVE_INVOICE_CALLBACK = "ReceiveInvoice"
RECEIVE_HIST_CALLBACK = "ReceiveHist:"
RECEIVE_ASSET_CALLBACK = "ReceiveAsset:"
RECEIVE_CHANGE_AMOUNT_CALLBACK = "ReceiveChangeAmount"
RECEIVE_CHANGE_ASSET_CALLBACK = "ReceiveChangeAsset"


def _get_history_store() -> ReceiveHistoryStore | None:
    client = faststream_tools.REDIS_CLIENT
    if client is None:
        return None
    return ReceiveHistoryStore(client)


@router.callback_query(F.data == "Receive")
async def cmd_receive(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    repo = app_context.repository_factory.get_wallet_repository(session)
    wallet = await repo.get_default_wallet(callback.from_user.id)

    if not wallet:
        await callback.answer(
            my_gettext(callback, "wallet_not_found", app_context=app_context),
            show_alert=True,
        )
        return

    account_id = wallet.public_key
    msg = my_gettext(callback, "my_address", (account_id,), app_context=app_context)
    qr_buffer = BytesIO()
    create_beautiful_code(qr_buffer, account_id)
    send_file = BufferedInputFile(qr_buffer.getvalue(), filename=f"{account_id}.png")

    user_id = get_user_id(callback)
    await clear_state(state)
    await _send_receive_photo(
        user_id,
        msg,
        send_file,
        _build_receive_keyboard(user_id, app_context=app_context),
        app_context=app_context,
    )
    await callback.answer()


def _build_receive_keyboard(user_id, *, app_context: AppContext) -> types.InlineKeyboardMarkup:
    invoice_button = [
        InlineKeyboardButton(
            text=my_gettext(
                user_id, "receive_invoice_btn", app_context=app_context
            ),
            callback_data=RECEIVE_INVOICE_CALLBACK,
        )
    ]
    manage_assets_button = [
        InlineKeyboardButton(
            text=my_gettext(
                user_id, "manage_assets_msg", app_context=app_context
            ),
            callback_data="ManageAssetsMenu",
        )
    ]
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            invoice_button,
            manage_assets_button,
            get_return_button(user_id, app_context=app_context),
        ]
    )


async def _send_receive_photo(
    user_id: int,
    caption: str,
    photo: types.InputFile,
    reply_markup,
    *,
    app_context: AppContext,
):
    """Photo screen mirroring cmd_info_message send_file branch.

    cmd_info_message hardcodes the ManageAssets keyboard, so the tracked
    photo rendering is repeated here with a custom keyboard.
    Deletes the previous tracked message and clears last_message_id
    (fresh buttons are not validated against the photo message).
    """
    current_bot = app_context.bot
    storage_key = StorageKey(
        bot_id=current_bot.id, user_id=user_id, chat_id=user_id
    )
    data = await app_context.dispatcher.storage.get_data(key=storage_key)
    previous_message_id = int(data.get("last_message_id", 0))
    await current_bot.send_photo(
        user_id, photo=photo, caption=caption, reply_markup=reply_markup
    )
    if previous_message_id > 0:
        with suppress(TelegramBadRequest):
            await current_bot.delete_message(user_id, previous_message_id)
    await clear_last_message_id(user_id, app_context=app_context)


def _parse_callback_index(data: str | None, prefix: str) -> int | None:
    if not data or not data.startswith(prefix):
        return None
    try:
        return int(data[len(prefix) :])
    except ValueError:
        return None


def _build_amount_keyboard(
    user_id, entries: list[HistoryAmount], *, app_context: AppContext
) -> types.InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{entry.amount} {entry.asset_code}",
                callback_data=f"{RECEIVE_HIST_CALLBACK}{index}",
            )
        ]
        for index, entry in enumerate(entries)
    ]
    rows.append(get_return_button(user_id, app_context=app_context))
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


async def _cmd_enter_amount(
    user_id: int, state: FSMContext, session: AsyncSession, app_context: AppContext
) -> bool:
    """Show the amount screen. Reuses wallet/asset already stored in FSM."""
    fsm = await state.get_data()
    account_id = fsm.get("receive_account_id")
    if not account_id:
        repo = app_context.repository_factory.get_wallet_repository(session)
        wallet = await repo.get_default_wallet(user_id)
        if not wallet:
            return False
        account_id = wallet.public_key
        await state.update_data(receive_account_id=account_id)
    if not fsm.get("receive_asset_code"):
        await state.update_data(
            receive_asset_code=EURMTL_ASSET.code,
            receive_asset_issuer=EURMTL_ASSET.issuer,
        )
    store = _get_history_store()
    entries = await store.get_history(user_id) if store else []
    await state.update_data(
        receive_history=[(e.amount, e.asset_code, e.issuer) for e in entries]
    )
    await send_message(
        session,
        user_id,
        my_gettext(user_id, "receive_invoice_amount_msg", app_context=app_context),
        reply_markup=_build_amount_keyboard(user_id, entries, app_context=app_context),
        app_context=app_context,
    )
    await state.set_state(ReceiveInvoiceStates.entering_amount)
    return True


def _build_pay_uri(destination: str, amount_str: str, code: str, issuer: str | None) -> str:
    params = [
        f"destination={destination}",
        f"amount={amount_str}",
        f"asset_code={code}",
    ]
    if issuer:
        params.append(f"asset_issuer={issuer}")
    return "web+stellar:pay?" + "&".join(params)


async def _show_invoice(
    state: FSMContext, session: AsyncSession, app_context: AppContext, user_id: int
):
    """Render the ready invoice screen: QR with SEP-7 URI + badge."""
    fsm = await state.get_data()
    account_id = fsm["receive_account_id"]
    amount_str = float2str(my_float(fsm["receive_amount"]))
    code = fsm["receive_asset_code"]
    issuer = fsm.get("receive_asset_issuer")

    uri = _build_pay_uri(account_id, amount_str, code, issuer)
    qr_buffer = BytesIO()
    create_invoice_qr(qr_buffer, uri, f"{amount_str} {code}")
    photo = BufferedInputFile(qr_buffer.getvalue(), filename="invoice.png")

    msg = my_gettext(
        user_id, "receive_invoice_msg", (amount_str, code, account_id), app_context=app_context
    )
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=my_gettext(
                        user_id, "receive_change_amount", app_context=app_context
                    ),
                    callback_data=RECEIVE_CHANGE_AMOUNT_CALLBACK,
                ),
                InlineKeyboardButton(
                    text=my_gettext(
                        user_id, "receive_change_asset", app_context=app_context
                    ),
                    callback_data=RECEIVE_CHANGE_ASSET_CALLBACK,
                ),
            ],
            get_return_button(user_id, app_context=app_context),
        ]
    )
    await state.set_state(None)
    await _send_receive_photo(
        user_id, msg, photo, keyboard, app_context=app_context
    )

    store = _get_history_store()
    if store:
        await store.add(user_id, HistoryAmount(amount_str, code, issuer))


@router.callback_query(F.data == RECEIVE_INVOICE_CALLBACK)
async def cmd_receive_invoice(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    user_id = get_user_id(callback)
    await clear_state(state)
    ok = await _cmd_enter_amount(user_id, state, session, app_context)
    if not ok:
        await callback.answer(
            my_gettext(callback, "wallet_not_found", app_context=app_context),
            show_alert=True,
        )
        return
    await callback.answer()


@router.callback_query(F.data == RECEIVE_CHANGE_AMOUNT_CALLBACK)
async def cmd_receive_change_amount(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    user_id = get_user_id(callback)
    ok = await _cmd_enter_amount(user_id, state, session, app_context)
    if not ok:
        await callback.answer(
            my_gettext(callback, "wallet_not_found", app_context=app_context),
            show_alert=True,
        )
        return
    await callback.answer()


@router.message(ReceiveInvoiceStates.entering_amount, F.text)
async def cmd_receive_amount_input(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    user_id = get_user_id(message)
    try:
        amount_val = my_float(message.text)
    except (ValueError, AttributeError, TypeError):
        amount_val = 0.0
    if math.isinf(amount_val) or amount_val <= 0:
        await send_message(
            session,
            user_id,
            my_gettext(message, "bad_sum", app_context=app_context),
            reply_markup=get_kb_return(user_id, app_context=app_context),
            app_context=app_context,
        )
        return
    await state.update_data(receive_amount=float2str(amount_val))
    await _show_invoice(state, session, app_context, user_id)


@router.callback_query(F.data == RECEIVE_CHANGE_ASSET_CALLBACK)
async def cmd_receive_change_asset(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    user_id = get_user_id(callback)
    balance_use_case = app_context.use_case_factory.create_get_wallet_balance(session)
    balances: list[Balance] = await balance_use_case.execute(user_id)
    assets: list[tuple[str, str | None]] = []
    for balance in balances:
        if balance.is_native:
            continue
        pair = (balance.asset_code, balance.asset_issuer)
        if pair not in assets:
            assets.append(pair)
    assets.append((XLM_ASSET.code, None))
    await state.update_data(receive_assets=assets)
    await state.set_state(None)
    await send_message(
        session,
        user_id,
        my_gettext(user_id, "receive_invoice_asset_msg", app_context=app_context),
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=code,
                        callback_data=f"{RECEIVE_ASSET_CALLBACK}{index}",
                    )
                ]
                for index, (code, _issuer) in enumerate(assets)
            ]
            + [get_return_button(user_id, app_context=app_context)]
        ),
        app_context=app_context,
    )
    await callback.answer()


@router.callback_query(F.data.startswith(RECEIVE_ASSET_CALLBACK))
async def cmd_receive_asset_pick(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    user_id = get_user_id(callback)
    index = _parse_callback_index(callback.data, RECEIVE_ASSET_CALLBACK)
    fsm = await state.get_data()
    assets = fsm.get("receive_assets") or []
    if index is None or index >= len(assets):
        await callback.answer(
            my_gettext(callback, "bad_data", app_context=app_context),
            show_alert=True,
        )
        return
    code, issuer = assets[index]
    await state.update_data(receive_asset_code=code, receive_asset_issuer=issuer)
    await _show_invoice(state, session, app_context, user_id)
    await callback.answer()


@router.callback_query(F.data.startswith(RECEIVE_HIST_CALLBACK))
async def cmd_receive_history_pick(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    app_context: AppContext,
):
    user_id = get_user_id(callback)
    index = _parse_callback_index(callback.data, RECEIVE_HIST_CALLBACK)
    fsm = await state.get_data()
    history = fsm.get("receive_history") or []
    if index is None or index >= len(history):
        await callback.answer(
            my_gettext(callback, "bad_data", app_context=app_context),
            show_alert=True,
        )
        return
    amount, code, issuer = history[index]
    await state.update_data(
        receive_amount=amount, receive_asset_code=code, receive_asset_issuer=issuer
    )
    await _show_invoice(state, session, app_context, user_id)
    await callback.answer()


def create_qr_with_logo(qr_code_text, logo_img):
    # Создание QR-кода
    qr = qrcode.QRCode(
        version=5,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=1,
    )
    qr.add_data(qr_code_text)
    qr.make(fit=True)
    qr_code_img = qr.make_image(fill_color=decode_color("5A89B9")).convert("RGB")

    # Размещение логотипа в центре QR-кода
    pos = (
        (qr_code_img.size[0] - logo_img.size[0]) // 2 + 5,
        (qr_code_img.size[1] - logo_img.size[1]) // 2,
    )
    qr_code_img.paste(logo_img, pos)

    return qr_code_img


def create_image_with_text(
    text, font_path="DejaVuSansMono.ttf", font_size=30, image_size=(200, 50)
):
    # Создание пустого изображения
    image = Image.new("RGB", image_size, color="white")
    draw = ImageDraw.Draw(image)

    # Загрузка шрифта
    font = ImageFont.truetype(font_path, font_size)

    # Расчет позиции для размещения текста по центру с использованием textbbox
    textbox = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = textbox[2] - textbox[0], textbox[3] - textbox[1]

    # Автоуменьшение шрифта, чтобы бейдж влезал в одну строку
    while text_width > image_size[0] - 8 and font_size > 8:
        font_size -= 1
        font = ImageFont.truetype(font_path, font_size)
        textbox = draw.textbbox((0, 0), text, font=font)
        text_width, text_height = textbox[2] - textbox[0], textbox[3] - textbox[1]
    x = (image_size[0] - text_width) / 2
    y = (image_size[1] - text_height) / 2 - 5

    draw.text((x, y), text, font=font, fill=decode_color("C1D9F9"))

    # Размещение рамки
    xy = [0, 0, image_size[0] - 1, image_size[1] - 1]
    draw.rectangle(xy, outline=decode_color("C1D9F9"), width=2)

    return image


def create_invoice_qr(file_name, uri, badge_text):
    """Invoice QR: SEP-7 payload with one-line amount badge in the center.

    Badge is narrow (2 digits + asset code) so version stays small and
    error correction keeps working around the logo hole.
    """
    badge_img = create_image_with_text(f" {badge_text} ", font_size=30, image_size=(190, 46))
    qr_with_logo_img = create_qr_with_logo(uri, badge_img)
    qr_with_logo_img.save(file_name, format="PNG")


def decode_color(color):
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def create_beautiful_code(file_name, address):
    logo_img = create_image_with_text(f"{address[:4]}..{address[-4:]}")
    qr_with_logo_img = create_qr_with_logo(address, logo_img)
    qr_with_logo_img.save(file_name, format="PNG")


if __name__ == "__main__":
    create_beautiful_code(
        "qr_with_logo.png", "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    )
    codes = (
        "GDWZR66DHAHLC4WKEUEDV6G6QOB5XEUQAXSY37MQRMRJEPP5FRGYGXHM",
        "GB7CUEY263TP7DH5QQFZGK3AN64TR5QPUXVS243AQFB3FZMYZSBPUFZJ",
        "GCVSF2B2B6LWO27WYM3PNTB4QJXWR6B7C7MKXYWR6TRSFSKODICDSIGY",
        "GAY3OXIYBKUC3QPVJ6XXZHY3PBOBOSBGZVLTNUNXGJR3WD7YVMNBEXDB",
        "GBXK5S6KOGRRCIFGSPMGUADKE3CABABP5UAXSO4Z77VGL4Y5CGCTQ3XS",
        "GCF4BBEUYSC2E353FNJ63USZOBHBVCP4ORP623F2CE5T7A4UPCG45LAJ",
        "GAZEFASTL4P7A6ERCSHKWDCKBQVGA4R3V5336ILQF4MSALSAH3VMGHIW",
        "GCY5UPKTZKY7RIS3ERMUX26TFKKJAHRZHGV7LUC5PT5I24LYMUMRRPDG",
        "GCU7E7MKN4BPBJTQI4TYVLRKPWYTT2CLAPDKKB72JV7JHDBZDOUROPXE",
        "GDLZOJGRIM5NGW4EO6SLJD7G6LDHJV7L2IO2AGVZ3YB45MRPOBIAOGJA",
        "GAFGSGW4B2LAUCERFLT5NKEQOBMEKXDGPDNXODP7PN4JMWYEBYMEVENT",
        "GATMFFGLVABYICXTVPKNDBNDLWHGGHVUKTGD7ME6HVFQ6V5OAB2IO3OE",
    )

    for code in codes:
        create_beautiful_code(f"{code}.png", code)
