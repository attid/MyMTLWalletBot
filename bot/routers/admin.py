import os
from contextlib import suppress
from datetime import datetime, timedelta

from aiogram import Router, types, Bot, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
from routers.inout import get_usdt_balance


class ExitState(StatesGroup):
    need_exit = State()


router = Router()
router.message.filter(F.chat.type == "private")
router.message.filter(F.chat.id.in_(config.admins))


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
    await cmd_send_file(app_context.bot, message, "mmwb.log")
    await cmd_send_file(app_context.bot, message, "mmwb_check_transaction.log")


@router.message(Command(commands=["err"]))
async def cmd_err(message: types.Message, app_context: AppContext):
    await cmd_send_file(app_context.bot, message, "MyMTLWallet_bot.err")


@router.message(Command(commands=["clear"]))
async def cmd_clear(message: types.Message):
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
        lines.append(f"{wallet.public_key} ({', '.join(labels)})")
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
    with suppress(TelegramBadRequest):
        chat = await app_context.bot.get_chat(215155653)
        await message.answer(chat.json())
    with suppress(TelegramBadRequest):
        chat = await app_context.bot.get_chat(5687567734)
        await message.answer(chat.json())
