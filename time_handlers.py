from aiogram import Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import fb
from utils.aiogram_utils import cmd_info_message


async def cmd_send_message_1m(dp: Dispatcher):
    for record in fb.execsql('select message_id, user_message, keyboard, user_id, was_send ' +
                             'from mymtlwalletbot_messages where was_send = 0'):
        await cmd_info_message(record[3], record[1], None)
        # await dp.bot.send_message(record[3], record[1], disable_web_page_preview=True)

        fb.execsql('update mymtlwalletbot_messages set was_send = 1 where message_id = ?', (record[0],))


def scheduler_jobs(scheduler: AsyncIOScheduler, dp):
    scheduler.add_job(cmd_send_message_1m, "interval", seconds=10, args=(dp,))
