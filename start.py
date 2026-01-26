import asyncio
import warnings

# Suppress Pydantic warning about 'model_' protected namespace (common in aiogram types)
warnings.filterwarnings(
    "ignore", message=".*has conflict with protected namespace .model_."
)

import uvloop
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from middleware.retry import RetryRequestMiddleware
from routers.inout import usdt_worker
from routers.monitoring import register_handlers
import sentry_sdk
from contextlib import suppress
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
    BotCommandScopeAllPrivateChats,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from sqlalchemy.orm import sessionmaker
from sulguk import AiogramSulgukMiddleware  # type: ignore[import-untyped]
from other.config_reader import config
from middleware.db import DbSessionMiddleware
from middleware.old_buttons import CheckOldButtonCallbackMiddleware
from middleware.log import LogButtonClickCallbackMiddleware, log_worker
from routers.cheque import cheque_worker
from routers import (
    add_wallet,
    admin,
    common_start,
    common_setting,
    mtltools,
    receive,
    trade,
    send,
    sign,
    swap,
    inout,
    cheque,
    mtlap,
    fest,
    uri,
    ton,
    notification_settings,
)
from routers import wallet_setting, common_end
from routers.bsn import bsn_router
from loguru import logger
from other.faststream_tools import start_broker, stop_broker
from infrastructure.scheduler.job_scheduler import scheduler_jobs
from infrastructure.utils.async_utils import setup_async_utils


# https://docs.aiogram.dev/en/latest/quick_start.html
# https://docs.aiogram.dev/en/dev-3.x/dispatcher/filters/index.html
# https://surik00.gitbooks.io/aiogram-lessons/content/chapter3.html
# https://mastergroosha.github.io/aiogram-3-guide/buttons/

from infrastructure.services.app_context import AppContext
from infrastructure.services.localization_service import LocalizationService
from middleware.app_context import AppContextMiddleware
from middleware.localization import LocalizationMiddleware


@logger.catch
async def bot_add_routers(
    bot: Bot,
    dp: Dispatcher,
    db_pool: sessionmaker,
    app_context: AppContext,
    localization_service: LocalizationService,
):
    bot.session.middleware(AiogramSulgukMiddleware())

    # DI Middlewares
    dp.message.middleware(AppContextMiddleware(app_context))
    dp.callback_query.middleware(AppContextMiddleware(app_context))
    dp.inline_query.middleware(AppContextMiddleware(app_context))

    dp.message.middleware(LocalizationMiddleware(localization_service))
    dp.callback_query.middleware(LocalizationMiddleware(localization_service))
    dp.inline_query.middleware(LocalizationMiddleware(localization_service))

    dp.callback_query.middleware(LogButtonClickCallbackMiddleware())
    dp.callback_query.middleware(CheckOldButtonCallbackMiddleware(db_pool))
    dp.message.middleware(DbSessionMiddleware(db_pool, localization_service))
    dp.callback_query.middleware(DbSessionMiddleware(db_pool, localization_service))
    dp.inline_query.middleware(DbSessionMiddleware(db_pool, localization_service))

    dp.include_router(common_start.router)  # first # first
    dp.include_router(cheque.router)  # first
    dp.include_router(uri.router)  # first
    dp.include_router(wallet_setting.router)  # first
    dp.include_router(notification_settings.router)  # first

    dp.include_router(fest.router)
    dp.include_router(sign.router)
    dp.include_router(add_wallet.router)
    dp.include_router(admin.router)
    dp.include_router(common_setting.router)
    dp.include_router(mtltools.router)
    dp.include_router(receive.router)
    dp.include_router(trade.router)
    dp.include_router(send.router)
    dp.include_router(swap.router)
    dp.include_router(inout.router)
    dp.include_router(ton.router)
    dp.include_router(mtlap.router)
    dp.include_router(bsn_router)
    register_handlers(dp, bot)

    # always the last
    dp.include_router(common_end.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown_dispatcher)


async def set_commands(bot: Bot):
    commands_clear: list[BotCommand] = []
    commands_private = [
        BotCommand(
            command="start",
            description="Start or ReStart bot",
        ),
        BotCommand(
            command="change_wallet",
            description="Switch to another address",
        ),
        BotCommand(
            command="send",
            description="Send tokens",
        ),
        BotCommand(
            command="create_cheque",
            description="Create cheque",
        ),
    ]
    # if 'test' in sys.argv:
    #     commands_private.append(BotCommand(
    #         command="delete_all",
    #         description="Delete all data",
    #     ))
    commands_admin = commands_private + [
        BotCommand(
            command="restart",
            description="ReStart bot",
        ),
        BotCommand(
            command="fee",
            description="check fee",
        ),
        BotCommand(
            command="horizon",
            description="change horizon",
        ),
        BotCommand(
            command="horizon_rx",
            description="change horizon_rw",
        ),
    ]

    await bot.set_my_commands(commands=commands_clear, scope=BotCommandScopeDefault())
    await bot.set_my_commands(
        commands=commands_private, scope=BotCommandScopeAllPrivateChats()
    )
    await bot.set_my_commands(
        commands=commands_admin, scope=BotCommandScopeChat(chat_id=config.admins[0])
    )


async def on_startup(bot: Bot, dispatcher: Dispatcher):
    app_context: AppContext = dispatcher["app_context"]
    await start_broker(app_context)
    await set_commands(bot)
    with suppress(TelegramBadRequest):
        await bot.send_message(chat_id=config.admins[0], text="Bot started")
    # fest.fest_menu = await gs_update_fest_menu()
    # Start Notification Service (Webhook Server)
    if app_context.notification_service:
        await app_context.notification_service.start_server()

    if config.test_mode:
        task_list = [
            # asyncio.create_task(cheque_worker(app_context)),
            # asyncio.create_task(log_worker(app_context)),
            # asyncio.create_task(events_worker(global_data.db_pool, dp=dispatcher)),
        ]
    else:
        # Import db_pool here? accessing from app_context.db_pool
        task_list = [
            asyncio.create_task(cheque_worker(app_context)),
            asyncio.create_task(log_worker(app_context)),
            asyncio.create_task(usdt_worker(bot, app_context)),
        ]

        # Add notification sync task
        if app_context.notification_service:
            task_list.append(
                asyncio.create_task(
                    app_context.notification_service.sync_subscriptions()
                )
            )

    dispatcher["task_list"] = task_list

    # config.fest_menu = await load_fest_info()


async def on_shutdown_dispatcher(dispatcher: Dispatcher, bot: Bot):
    await stop_broker()
    with suppress(TelegramBadRequest):
        await bot.send_message(chat_id=config.admins[0], text="Bot stopped")

    # Stop Notification Service
    app_context: AppContext = dispatcher["app_context"]
    if app_context.notification_service:
        await app_context.notification_service.stop()

    task_list = dispatcher.get("task_list", [])
    if task_list:
        for task in task_list:
            task.cancel()


async def main():
    if len(config.sentry_dsn) > 20:
        sentry_sdk.init(
            dsn=config.sentry_dsn,
            traces_sample_rate=1.0,
            profiles_sample_rate=1.0,
        )

    # Creating DB connections pool
    from db.db_pool import db_pool

    default_bot_properties = DefaultBotProperties(parse_mode="HTML")
    session: AiohttpSession = AiohttpSession()
    session.middleware(RetryRequestMiddleware())
    if config.test_mode:
        bot = Bot(
            token=config.test_bot_token.get_secret_value(),
            default=default_bot_properties,
            session=session,
        )
        print("start test")
    else:
        bot = Bot(
            token=config.bot_token.get_secret_value(),
            default=default_bot_properties,
            session=session,
        )

    storage = RedisStorage.from_url(config.redis_url)
    dp = Dispatcher(storage=storage)
    scheduler = AsyncIOScheduler(
        timezone="Europe/Podgorica"
    )  # str(tzlocal.get_localzone())
    scheduler.start()

    # Create Queues
    cheque_queue = asyncio.Queue()
    log_queue = asyncio.Queue()

    # Initialize Services
    from infrastructure.services.app_context import AppContext
    from infrastructure.services.localization_service import LocalizationService
    from infrastructure.persistence.repository_factory import (
        SqlAlchemyRepositoryFactory,
    )
    from infrastructure.services.stellar_service import StellarService

    from infrastructure.services.encryption_service import EncryptionService
    from services.ton_service import TonService
    from infrastructure.services.notification_service import NotificationService

    localization_service = LocalizationService(db_pool)
    await localization_service.load_languages(f"{config.start_path}/langs/")

    repository_factory = SqlAlchemyRepositoryFactory()
    stellar_service = StellarService(horizon_url=config.horizon_url)
    encryption_service = EncryptionService()
    ton_service = TonService()

    # Create UseCaseFactory for DI
    from infrastructure.factories.use_case_factory import UseCaseFactory
    from core.constants import CHEQUE_PUBLIC_KEY

    use_case_factory = UseCaseFactory(
        repository_factory, stellar_service, encryption_service, CHEQUE_PUBLIC_KEY
    )

    from infrastructure.services.notification_service import NotificationService
    from infrastructure.services.notification_history_service import NotificationHistoryService

    notification_history = NotificationHistoryService(ttl_hours=12, max_per_user=50)

    notification_service = NotificationService(
        config, db_pool, bot, localization_service, dp, notification_history
    )

    app_context = AppContext(
        bot=bot,
        db_pool=db_pool,
        admin_id=config.admins[0],
        cheque_queue=cheque_queue,
        log_queue=log_queue,
        repository_factory=repository_factory,
        stellar_service=stellar_service,
        ton_service=ton_service,
        encryption_service=encryption_service,
        localization_service=localization_service,
        dispatcher=dp,
        use_case_factory=use_case_factory,
        notification_service=notification_service,
        notification_history=notification_history,
    )

    dp["app_context"] = app_context

    setup_async_utils(bot, config.admins[0])
    scheduler_jobs(scheduler, db_pool, dp, app_context)

    await bot_add_routers(bot, dp, db_pool, app_context, localization_service)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    logger.add("logs/mmwb.log", rotation="1 MB")
    try:
        uvloop.install()
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.error("Exit")
