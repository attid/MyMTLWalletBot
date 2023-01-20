import asyncio
import sys

import time_handlers
from config_reader import config
from middleware.old_buttons import CheckOldButtonCallbackMiddleware
from utils.aiogram_utils import bot, dp, scheduler
from routers import add_wallet, admin, common_start, common_setting, mtltools, receive, sale, send, sign, swap
from routers import veche, wallet_setting, common_end
from loguru import logger


# https://docs.aiogram.dev/en/latest/quick_start.html
# https://docs.aiogram.dev/en/dev-3.x/dispatcher/filters/index.html
# https://surik00.gitbooks.io/aiogram-lessons/content/chapter3.html
# https://mastergroosha.github.io/aiogram-3-guide/buttons/

# Запуск бота
@logger.catch
async def main():
    logger.add("MMWB.log", rotation="1 MB", level='INFO')
    dp.callback_query.middleware(CheckOldButtonCallbackMiddleware())

    dp.include_router(veche.router) # first
    dp.include_router(common_start.router)

    dp.include_router(sign.router)
    dp.include_router(add_wallet.router)
    dp.include_router(admin.router)
    dp.include_router(common_setting.router)
    dp.include_router(mtltools.router)
    dp.include_router(receive.router)
    dp.include_router(sale.router)
    dp.include_router(send.router)
    dp.include_router(swap.router)
    dp.include_router(wallet_setting.router)

    # always the last
    dp.include_router(common_end.router)

    if 'test' in sys.argv:
        pass
    else:
        scheduler.start()
        time_handlers.scheduler_jobs(scheduler, dp)

    # Запускаем бота и пропускаем все накопленные входящие
    # Да, этот метод можно вызвать даже если у вас поллинг
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
