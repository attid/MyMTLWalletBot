import html
import math
import os
import secrets
from contextlib import suppress
from datetime import datetime, timedelta

from loguru import logger

from aiogram import Router, types, Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from stellar_sdk import Keypair
from stellar_sdk.exceptions import BaseHorizonError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import (
    CHEQUE_PUBLIC_KEY,
    EURMTL_ASSET,
    MTL_ASSET,
    SATSMTL_ASSET,
    USDM_ASSET,
    USDC_ASSET,
    BTCMTL_ASSET,
    XLM_ASSET,
)

from db.models import (
    MyMtlWalletBotUsers,
    MyMtlWalletBot,
    MyMtlWalletBotTransactions,
    MyMtlWalletBotCheque,
    MyMtlWalletBotLog,
)
from other.config_reader import config, horizont_urls

# from other.global_data import global_data
from other.stellar_tools import async_stellar_check_fee
from infrastructure.services.app_context import AppContext
from infrastructure.utils.telegram_utils import send_message
from routers.inout import get_usdt_balance


class ExitState(StatesGroup):
    need_exit = State()


router = Router()
router.message.filter(F.chat.type == "private")
router.message.filter(F.chat.id.in_(config.admins))


# --- Admin payout commands (/chequepay, /withdraw) ---

PAYOUT_CB_PREFIX = "AdminPayout:"
PAYOUT_CB_APPROVE = PAYOUT_CB_PREFIX + "go:"
PAYOUT_CB_CANCEL = PAYOUT_CB_PREFIX + "no:"

PAYOUT_SOURCE_MASTER = "master"
PAYOUT_SOURCE_CHEQUE = "cheque"

WITHDRAW_ASSETS = {
    asset.code: asset
    for asset in (
        EURMTL_ASSET,
        MTL_ASSET,
        SATSMTL_ASSET,
        USDM_ASSET,
        USDC_ASSET,
        BTCMTL_ASSET,
    )
}

# Pending payout confirmations keyed by one-time token (admin-only flow).
# Lost on bot restart: stale buttons answer "истекло" and no payment runs.
_pending_payouts: dict[str, dict] = {}

PAYOUT_CB_APPROVE_LEN = len(PAYOUT_CB_APPROVE)
PAYOUT_CB_CANCEL_LEN = len(PAYOUT_CB_CANCEL)


def _payout_amount_str(amount_part: str) -> str | None:
    """Normalize a user-entered amount to a 7-decimal Stellar string."""
    try:
        value = float(amount_part)
    except ValueError:
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return f"{value:.7f}"


def _validate_payout_address(address: str) -> bool:
    try:
        Keypair.from_public_key(address)
    except Exception:
        return False
    return True


def _payout_source_label(source: str) -> str:
    if source == PAYOUT_SOURCE_CHEQUE:
        return f"чековый счёт <code>{CHEQUE_PUBLIC_KEY}</code>"
    return "основной счёт (мастер)"


def _payout_summary_text(
    source: str, address: str, amount_str: str, asset_code: str, memo: str | None
) -> str:
    lines = [
        "<b>Подтвердите перевод</b>",
        f"Откуда: {_payout_source_label(source)}",
        f"Куда: <code>{html.escape(address)}</code>",
        f"Сумма: <b>{amount_str} {asset_code}</b>",
    ]
    if memo:
        lines.append(f"Memo: {html.escape(memo)}")
    return "\n".join(lines)


def _build_payout_confirm_keyboard(token: str) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✅ Отправить", callback_data=PAYOUT_CB_APPROVE + token
                ),
                types.InlineKeyboardButton(
                    text="❌ Отмена", callback_data=PAYOUT_CB_CANCEL + token
                ),
            ]
        ]
    )


def _payout_asset_issuer(asset_code: str) -> str | None:
    if asset_code == XLM_ASSET.code:
        return None
    asset = WITHDRAW_ASSETS.get(asset_code)
    return asset.issuer if asset else None


async def _decrypt_master_secret(wallet, app_context: AppContext) -> str | None:
    """Decrypt master secret: crypto_v2 free-mode first, legacy fallback."""
    secret: str | None = None
    if getattr(wallet, "wallet_crypto_v2", None):
        secret = app_context.encryption_service.decrypt_wallet_secret(
            wallet.wallet_crypto_v2, pin=None
        )
    if secret is None and getattr(wallet, "secret_key", None):
        secret = app_context.encryption_service.decrypt(wallet.secret_key, "0")
    return secret


async def _execute_admin_payout(
    session: AsyncSession,
    app_context: AppContext,
    source: str,
    address: str,
    amount_str: str,
    asset_code: str,
    memo: str | None,
) -> tuple[bool, str]:
    """Sign and submit the payout. Returns (success, tx_hash_or_error)."""
    wallet_repo = app_context.repository_factory.get_wallet_repository(session)
    master_wallet = await wallet_repo.get_default_wallet(0)
    if not master_wallet:
        return False, "Master wallet not found"

    secret = await _decrypt_master_secret(master_wallet, app_context)
    if not secret:
        return False, "Failed to decrypt master secret"

    source_pk = (
        CHEQUE_PUBLIC_KEY if source == PAYOUT_SOURCE_CHEQUE else master_wallet.public_key
    )
    asset_issuer = _payout_asset_issuer(asset_code)
    if asset_code != XLM_ASSET.code and asset_issuer is None:
        return False, f"Unsupported asset: {asset_code}"

    xdr = await app_context.stellar_service.build_payment_transaction(
        source_account_id=source_pk,
        destination_account_id=address,
        asset_code=asset_code,
        asset_issuer=asset_issuer,
        amount=amount_str,
        memo=memo,
    )
    signed_xdr = await app_context.stellar_service.sign_xdr(xdr, secret)

    try:
        submit_result = await app_context.stellar_service.submit_transaction(signed_xdr)
    except BaseHorizonError as ex:
        from routers.sign import format_horizon_send_error

        return False, format_horizon_send_error(ex)

    if not submit_result.get("successful", False):
        error_detail = submit_result.get("error") or "Horizon rejected the transaction"
        logger.warning(
            f"Admin payout rejected: {asset_code} {amount_str}: {error_detail}"
        )
        return False, error_detail
    return True, submit_result.get("hash") or ""


async def _handle_payout_command(
    message: types.Message,
    session: AsyncSession,
    app_context: AppContext,
    *,
    source: str,
    memo_allowed: bool,
) -> None:
    if not message.text or message.from_user is None:
        return
    args = message.text.split()
    if memo_allowed:
        usage = (
            "Использование: /withdraw <адрес> <сумма> <ассет> [memo]\n"
            "Ассеты: " + ", ".join([*WITHDRAW_ASSETS, XLM_ASSET.code])
        )
        min_args = 4
    else:
        usage = "Использование: /chequepay <адрес> <сумма>"
        min_args = 3
    if len(args) < min_args:
        await message.answer(usage)
        return

    address = args[1]
    if not _validate_payout_address(address):
        await message.answer("Некорректный Stellar-адрес")
        return

    amount_str = _payout_amount_str(args[2])
    if amount_str is None:
        await message.answer("Некорректная сумма")
        return

    memo: str | None = None
    if memo_allowed:
        asset_code = args[3].upper()
        if asset_code != XLM_ASSET.code and asset_code not in WITHDRAW_ASSETS:
            await message.answer(
                "Неизвестный ассет. Доступны: "
                + ", ".join([*WITHDRAW_ASSETS, XLM_ASSET.code])
            )
            return
        if len(args) > 4:
            memo = " ".join(args[4:])
            if len(memo.encode()) > 28:
                await message.answer("Memo слишком длинное (максимум 28 байт)")
                return
    else:
        asset_code = EURMTL_ASSET.code

    token = secrets.token_hex(4)
    _pending_payouts[token] = {
        "admin_id": message.from_user.id,
        "source": source,
        "address": address,
        "amount": amount_str,
        "asset": asset_code,
        "memo": memo,
    }

    await send_message(
        session,
        message.from_user.id,
        _payout_summary_text(source, address, amount_str, asset_code, memo),
        reply_markup=_build_payout_confirm_keyboard(token),
        need_new_msg=True,
        app_context=app_context,
    )


async def _admin_payout_guard(callback: types.CallbackQuery) -> bool:
    if not callback.from_user or callback.from_user.id not in config.admins:
        await callback.answer("Только для админов", show_alert=True)
        return False
    return True


def _pop_pending_payout(data: str, prefix_len: int):
    return _pending_payouts.pop(data[prefix_len:], None)


@router.callback_query(F.data.startswith(PAYOUT_CB_APPROVE))
async def cb_admin_payout_approve(
    callback: types.CallbackQuery,
    session: AsyncSession,
    app_context: AppContext,
):
    if not await _admin_payout_guard(callback):
        return
    payout = _pop_pending_payout(callback.data or "", PAYOUT_CB_APPROVE_LEN)
    if not payout or payout.get("admin_id") != callback.from_user.id:
        await callback.answer(
            "Подтверждение истекло, создайте выплату заново", show_alert=True
        )
        return
    await callback.answer()
    success, detail = await _execute_admin_payout(
        session,
        app_context,
        payout["source"],
        payout["address"],
        payout["amount"],
        payout["asset"],
        payout["memo"],
    )
    if success:
        text = (
            "✅ Перевод отправлен\n"
            f"Сумма: {payout['amount']} {payout['asset']}\n"
            f"Куда: <code>{html.escape(payout['address'])}</code>\n"
            f"Hash: <code>{detail}</code>"
        )
    else:
        text = f"❌ Ошибка перевода\n{html.escape(detail)}"
    await send_message(session, callback.from_user.id, text, app_context=app_context)


@router.callback_query(F.data.startswith(PAYOUT_CB_CANCEL))
async def cb_admin_payout_cancel(
    callback: types.CallbackQuery,
    session: AsyncSession,
    app_context: AppContext,
):
    if not await _admin_payout_guard(callback):
        return
    payout = _pop_pending_payout(callback.data or "", PAYOUT_CB_CANCEL_LEN)
    if not payout or payout.get("admin_id") != callback.from_user.id:
        await callback.answer("Подтверждение истекло", show_alert=True)
        return
    await callback.answer()
    await send_message(session, callback.from_user.id, "❌ Отменено", app_context=app_context)


@router.message(Command(commands=["chequepay"]))
async def cmd_chequepay(
    message: types.Message, session: AsyncSession, app_context: AppContext
):
    await _handle_payout_command(
        message, session, app_context, source=PAYOUT_SOURCE_CHEQUE, memo_allowed=False
    )


@router.message(Command(commands=["withdraw"]))
async def cmd_withdraw(
    message: types.Message, session: AsyncSession, app_context: AppContext
):
    await _handle_payout_command(
        message, session, app_context, source=PAYOUT_SOURCE_MASTER, memo_allowed=True
    )


def _pin_label(use_pin: int) -> str:
    if use_pin == 0:
        return "no pin"
    if use_pin == 1:
        return "pin"
    if use_pin == 2:
        return "password"
    if use_pin == 10:
        return "read-only"
    return "unknown"


@router.message(Command(commands=["stats"]))
async def cmd_stats(message: types.Message, session: AsyncSession):
    user_count = (
        await session.execute(select(func.count()).select_from(MyMtlWalletBotUsers))
    ).scalar() or 0
    wallet_count = (
        await session.execute(select(func.count()).select_from(MyMtlWalletBot))
    ).scalar() or 0
    transaction_count = (
        await session.execute(
            select(func.count()).select_from(MyMtlWalletBotTransactions)
        )
    ).scalar() or 0
    cheque_count = (
        await session.execute(select(func.count()).select_from(MyMtlWalletBotCheque))
    ).scalar() or 0
    log_count = (
        await session.execute(select(func.count()).select_from(MyMtlWalletBotLog))
    ).scalar() or 0

    # Активность за последние 24 часа и неделю
    activity_24h = (
        await session.execute(
            select(func.count())
            .select_from(MyMtlWalletBotLog)
            .filter(MyMtlWalletBotLog.log_dt > datetime.now() - timedelta(days=1))
        )
    ).scalar() or 0
    activity_7d = (
        await session.execute(
            select(func.count())
            .select_from(MyMtlWalletBotLog)
            .filter(MyMtlWalletBotLog.log_dt > datetime.now() - timedelta(days=7))
        )
    ).scalar() or 0

    # Уникальные пользователи за последние 24 часа и неделю
    unique_users_24h = (
        await session.execute(
            select(func.count(MyMtlWalletBotLog.user_id.distinct())).filter(
                MyMtlWalletBotLog.log_dt > datetime.now() - timedelta(days=1)
            )
        )
    ).scalar() or 0
    unique_users_7d = (
        await session.execute(
            select(func.count(MyMtlWalletBotLog.user_id.distinct())).filter(
                MyMtlWalletBotLog.log_dt > datetime.now() - timedelta(days=7)
            )
        )
    ).scalar() or 0

    # Топ 5 операций за неделю
    top_operations_query = (
        select(
            MyMtlWalletBotLog.log_operation_info,
            func.count(MyMtlWalletBotLog.log_operation_info).label("count"),
        )
        .filter(MyMtlWalletBotLog.log_dt > datetime.now() - timedelta(days=7))
        .group_by(MyMtlWalletBotLog.log_operation_info)
        .order_by(func.count(MyMtlWalletBotLog.log_operation_info).desc())
        .limit(5)
    )
    top_operations = (await session.execute(top_operations_query)).all()
    top_operations_str = "\n".join([f"{op}: {count}" for op, count in top_operations])

    stats_message = (
        f"**Статистика бота**\n\n"
        f"**Общая статистика:**\n"
        f"Пользователи: {user_count}\n"
        f"Кошельки: {wallet_count}\n"
        f"Транзакции: {transaction_count}\n"
        f"Чеки: {cheque_count}\n"
        f"Логи: {log_count}\n\n"
        f"**Активность:**\n"
        f"За 24 часа: {activity_24h} действий от {unique_users_24h} уник. пользователей\n"
        f"За 7 дней: {activity_7d} действий от {unique_users_7d} уник. пользователей\n\n"
        f"**Топ-5 операций за неделю:**\n{top_operations_str}"
    )

    await message.answer(stats_message)


@router.message(Command(commands=["exit"]))
@router.message(Command(commands=["restart"]))
async def cmd_exit(message: types.Message, state: FSMContext, session: AsyncSession):
    my_state = await state.get_state()
    if message.from_user and message.from_user.username == "itolstov":
        if my_state == ExitState.need_exit:
            await state.set_state(None)
            await message.reply("Chao :[[[")
            # Skip exit in test mode
            if not os.getenv("PYTEST_CURRENT_TEST"):
                exit()
        else:
            await state.set_state(ExitState.need_exit)
            await message.reply(":'[")


@router.message(Command(commands=["resync"]))
async def cmd_resync(message: types.Message, app_context: AppContext):
    if message.from_user and message.from_user.username == "itolstov":
        if app_context.notification_service:
            await message.reply("Starting subscription resync...")
            try:
                await app_context.notification_service.sync_subscriptions()
                await message.reply("✅ Resync completed successfully!")
            except Exception as e:
                await message.reply(f"❌ Resync failed: {e}")
        else:
            await message.reply("⚠️ Notification service not available")


@router.message(Command(commands=["horizon"]))
async def cmd_horizon(message: types.Message, state: FSMContext, session: AsyncSession):
    if message.from_user and message.from_user.username == "itolstov":
        if config.horizon_url in horizont_urls:
            config.horizon_url = horizont_urls[
                (horizont_urls.index(config.horizon_url) + 1) % len(horizont_urls)
            ]
        else:
            horizont_urls.append(config.horizon_url)
            config.horizon_url = horizont_urls[0]
        await message.reply(f"Horizon url: {config.horizon_url}")


@router.message(Command(commands=["horizon_rw"]))
async def cmd_horizon_rw(
    message: types.Message, state: FSMContext, session: AsyncSession
):
    if message.from_user and message.from_user.username == "itolstov":
        if config.horizon_url_rw in horizont_urls:
            config.horizon_url_rw = horizont_urls[
                (horizont_urls.index(config.horizon_url_rw) + 1) % len(horizont_urls)
            ]
        else:
            horizont_urls.append(config.horizon_url_rw)
            config.horizon_url_rw = horizont_urls[0]
        await message.reply(f"Horizon url: {config.horizon_url_rw}")


async def cmd_send_file(bot: Bot, message: types.Message, filename):
    if os.path.isfile(filename):
        await bot.send_document(message.chat.id, types.FSInputFile(filename))


async def cmd_delete_file(filename):
    if os.path.isfile(filename):
        # Skip file deletion in test mode
        if not os.getenv("PYTEST_CURRENT_TEST"):
            os.remove(filename)


@router.message(Command(commands=["log"]))
async def cmd_log(message: types.Message, app_context: AppContext):
    if message.from_user and message.from_user.username == "itolstov":
        await cmd_send_file(app_context.bot, message, "mmwb.log")
        await cmd_send_file(app_context.bot, message, "mmwb_check_transaction.log")


@router.message(Command(commands=["err"]))
async def cmd_err(message: types.Message, app_context: AppContext):
    if message.from_user and message.from_user.username == "itolstov":
        await cmd_send_file(app_context.bot, message, "MyMTLWallet_bot.err")


@router.message(Command(commands=["clear"]))
async def cmd_clear(message: types.Message):
    if message.from_user and message.from_user.username == "itolstov":
        await cmd_delete_file("MMWB.err")
        await cmd_delete_file("MMWB.log")


@router.message(Command(commands=["fee"]))
async def cmd_fee(message: types.Message):
    await message.answer("Комиссия (мин и мах) " + await async_stellar_check_fee())


@router.message(Command(commands=["user_wallets"]))
async def cmd_user_wallets(message: types.Message, session: AsyncSession):
    if not message.text:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /user_wallets @username_or_id")
        return

    target = args[1]
    user_id = None
    with suppress(ValueError):
        user_id = int(target)
    if user_id is None:
        user_name = target.lstrip("@").lower()
        user = (
            await session.execute(
                select(MyMtlWalletBotUsers).filter(
                    MyMtlWalletBotUsers.user_name == user_name
                )
            )
        ).scalar_one_or_none()
        if user is None:
            await message.answer("Пользователь не найден")
            return
        user_id = user.user_id

    wallets = (
        (
            await session.execute(
                select(MyMtlWalletBot).filter(MyMtlWalletBot.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    if not wallets:
        await message.answer("Кошельки не найдены")
        return

    lines = []
    for wallet in wallets:
        labels = []
        if wallet.default_wallet == 1:
            labels.append("main")
        if wallet.free_wallet == 1:
            labels.append("free")
        if wallet.need_delete == 1:
            labels.append("deleted")
        labels.append(_pin_label(wallet.use_pin or 0))
        address = wallet.public_key
        viewer_url = f"https://viewer.eurmtl.me/account/{address}"
        lines.append(
            f"<code>{address}</code> ({', '.join(labels)}) "
            f'(<a href="{viewer_url}">viewer</a>)'
        )
    await message.answer("\n".join(lines))


@router.message(Command(commands=["address_info"]))
async def cmd_address_info(message: types.Message, session: AsyncSession):
    if not message.text:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /address_info address")
        return

    address = args[1]
    wallet = (
        await session.execute(
            select(MyMtlWalletBot).filter(MyMtlWalletBot.public_key == address)
        )
    ).scalar_one_or_none()
    if wallet is None:
        await message.answer("Адрес не найден")
        return

    user = (
        await session.execute(
            select(MyMtlWalletBotUsers).filter(
                MyMtlWalletBotUsers.user_id == wallet.user_id
            )
        )
    ).scalar_one_or_none()
    if user is None:
        await message.answer(f"Владелец не найден (ID: {wallet.user_id})")
        return

    await message.answer(f"Владелец: {user.user_name} (ID: {user.user_id})")


@router.message(Command(commands=["delete_address"]))
async def cmd_delete_address(message: types.Message, session: AsyncSession):
    if not message.text:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /delete_address address")
        return

    address = args[1]
    wallet = (
        await session.execute(
            select(MyMtlWalletBot).filter(MyMtlWalletBot.public_key == address)
        )
    ).scalar_one_or_none()
    if wallet is None:
        await message.answer("Адрес не найден")
        return

    if wallet.need_delete == 1:
        await message.answer("Адрес уже помечен удалённым")
        return

    wallet.need_delete = 1
    await session.commit()
    await message.answer("Адрес помечен удалённым")


@router.message(Command(commands=["check_usdt"]))
async def cmd_check_usdt(message: types.Message, session: AsyncSession):
    if not message.text:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /check_usdt @username_or_id")
        return

    target = args[1]
    user_id = None
    with suppress(ValueError):
        user_id = int(target)

    query = select(MyMtlWalletBotUsers)
    if user_id is not None:
        query = query.filter(MyMtlWalletBotUsers.user_id == user_id)
    else:
        user_name = target.lstrip("@").lower()
        query = query.filter(MyMtlWalletBotUsers.user_name == user_name)

    user = (await session.execute(query)).scalar_one_or_none()

    if user is None:
        await message.answer("Пользователь не найден")
        return

    db_balance = user.usdt_amount or 0
    usdt_address = "Нет ключа"
    chain_balance = "N/A"

    if user.usdt and len(user.usdt) == 64:
        from other.tron_tools import tron_get_public

        try:
            # user.usdt stores private key
            usdt_address = tron_get_public(user.usdt)
            chain_balance_val = await get_usdt_balance(private_key=user.usdt)
            chain_balance = str(chain_balance_val)
        except Exception as e:
            chain_balance = f"Error: {e}"

    await message.answer(
        f"👤 User: {user.user_name} (ID: {user.user_id})\n"
        f"🔑 TRC20 Address: `{usdt_address}`\n"
        f"📚 DB Balance: {db_balance}\n"
        f"⛓️ Chain Balance: {chain_balance}"
    )


@router.message(Command(commands=["set_usdt"]))
async def cmd_set_usdt(message: types.Message, session: AsyncSession):
    if not message.text:
        return
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Использование: /set_usdt @username_or_id amount")
        return

    target = args[1]
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("Сумма должна быть целым числом")
        return

    user_id = None
    with suppress(ValueError):
        user_id = int(target)

    query = select(MyMtlWalletBotUsers)
    if user_id is not None:
        query = query.filter(MyMtlWalletBotUsers.user_id == user_id)
    else:
        user_name = target.lstrip("@").lower()
        query = query.filter(MyMtlWalletBotUsers.user_name == user_name)

    user = (await session.execute(query)).scalar_one_or_none()

    if user is None:
        await message.answer("Пользователь не найден")
        return

    old_balance = user.usdt_amount
    user.usdt_amount = amount
    await session.commit()

    await message.answer(
        f"✅ Баланс обновлен.\n"
        f"Пользователь: {user.user_name} (ID: {user.user_id})\n"
        f"Было: {old_balance}\n"
        f"Стало: {amount}"
    )


@router.message(Command(commands=["crypto_migration_status"]))
async def cmd_crypto_migration_status(message: types.Message, session: AsyncSession):
    base_filter = MyMtlWalletBot.need_delete == 0

    total_wallets = (
        await session.execute(
            select(func.count()).select_from(MyMtlWalletBot).filter(base_filter)
        )
    ).scalar() or 0

    migrated_wallets = (
        await session.execute(
            select(func.count())
            .select_from(MyMtlWalletBot)
            .filter(base_filter, MyMtlWalletBot.wallet_crypto_v2.is_not(None))
        )
    ).scalar() or 0

    pending_wallets = max(total_wallets - migrated_wallets, 0)

    pending_requires_user_pin = (
        await session.execute(
            select(func.count())
            .select_from(MyMtlWalletBot)
            .filter(
                base_filter,
                MyMtlWalletBot.wallet_crypto_v2.is_(None),
                MyMtlWalletBot.use_pin.in_([1, 2]),
            )
        )
    ).scalar() or 0

    pending_other = max(pending_wallets - pending_requires_user_pin, 0)
    progress_pct = (migrated_wallets / total_wallets * 100) if total_wallets else 0.0

    await message.answer(
        "🔐 Crypto v2 migration status\n"
        f"Total wallets: {total_wallets}\n"
        f"Migrated: {migrated_wallets} ({progress_pct:.1f}%)\n"
        f"Pending: {pending_wallets}\n"
        f"- Pending (requires user PIN/password): {pending_requires_user_pin}\n"
        f"- Pending (other): {pending_other}"
    )


@router.message(Command(commands=["help"]))
async def cmd_help(message: types.Message):
    await message.answer(
        "/stats — общая статистика\n"
        "/fee — комиссия сети\n"
        "/log | /err | /clear — логи/очистка\n"
        "/horizon | /horizon_rw — переключить horizon\n"
        "/user_wallets @user_or_id — кошельки пользователя\n"
        "/address_info address — найти владельца адреса\n"
        "/delete_address address — пометить адрес удалённым\n"
        "/usdt id — принудительный вывод USDT\n"
        "/usdt1 — автовывод первого в очереди\n"
        "/check_usdt @user — сверка баланса БД и блокчейна\n"
        "/set_usdt @user amount — установка баланса БД\n"
        "/chequepay <адрес> <сумма> — выплата EURMTL с чекового счёта\n"
        "/withdraw <адрес> <сумма> <ассет> [memo] — перевод с основного счёта\n"
        "/crypto_migration_status — прогресс миграции wallet_crypto_v2\n"
        "/balance — проверить баланс"
    )


# @router.message(Command(commands=["update"]))
# async def cmd_update(message: types.Message):
#     if message.from_user and message.from_user.username == "itolstov":
#         for rec in fb.execsql('select distinct m.user_id, m.user_name from mymtlwalletbot_user m where m.user_id > 0'):
#             try:
#                 username = await bot.get_chat(rec[0])
#                 if username.username:
#                     if username.username.lower() != rec[1]:
#                         fb.execsql('update mymtlwalletbot_user m set m.user_name = ? where m.user_id = ?',
#                                    (username.username.lower(), username.id))
#                         await message.answer(f'username {username.username}')
#             except Exception:  # ChatNotFound
#                 pass
#         await message.answer('done')


# @router.message(Command(commands=["update2"]))
# async def cmd_update2(message: types.Message):
#     if message.from_user and message.from_user.username == "itolstov":
#         select = fb.execsql('select distinct m.user_id, m.public_key from mymtlwalletbot m '
#                             'where m.user_id > 0 and m.default_wallet = 1 and m.free_wallet = 1')
#         await message.answer(str(len(select)))
#         i = 0
#         for rec in select:
#             i += 1
#             if i > 140:
#                 await message.answer(rec[1] + ' ' + str(i))
#             await stellar_find_claim(rec[1], rec[0])
#
#         await message.answer('done')


# @router.message(Command(commands=["update3"]))
# async def cmd_update3(message: types.Message):
#     if message.from_user and message.from_user.username == "itolstov":
#         select = fb.execsql('select distinct m.user_id, m.public_key, m.credit from mymtlwalletbot m '
#                             'where m.user_id > 0 and m.default_wallet = 1 and m.free_wallet = 1 and m.credit = 3')
#         await message.answer(str(len(select)))
#         await stellar_update_credit(select)
#         await message.answer(f'done 90')


@router.message(Command(commands=["test"]))
async def cmd_test(message: types.Message, app_context: AppContext):
    if message.from_user and message.from_user.username == "itolstov":
        with suppress(TelegramBadRequest):
            chat = await app_context.bot.get_chat(215155653)
            await message.answer(chat.json())
        with suppress(TelegramBadRequest):
            chat = await app_context.bot.get_chat(5687567734)
            await message.answer(chat.json())
