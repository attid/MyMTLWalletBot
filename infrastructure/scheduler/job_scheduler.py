from aiogram import Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db.db_pool import DatabasePool
from infrastructure.workers.message_worker import cmd_send_message_1m

def scheduler_jobs(scheduler: AsyncIOScheduler, db_pool: DatabasePool, dp: Dispatcher):
    scheduler.add_job(cmd_send_message_1m, "interval", seconds=10, args=(db_pool, dp), misfire_grace_time=60)
    # scheduler.add_job(cmd_send_message_events, "interval", seconds=8, args=(db_pool, dp), misfire_grace_time=60)
