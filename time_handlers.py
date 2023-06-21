from aiogram import Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

import fb
from routers.start_msg import cmd_info_message
from utils.lang_utils import set_last_message_id, my_gettext
from utils.stellar_utils import float2str


async def cmd_send_message_1m(dp: Dispatcher):
    for record in fb.execsql('select first 10 message_id, user_message, keyboard, user_id, was_send ' +
                             'from mymtlwalletbot_messages where was_send = 0'):
        try:
            await cmd_info_message(record[3], record[1], None)
        except Exception as ex:
            fb.execsql('update mymtlwalletbot_messages set was_send = 2 where message_id = ?', (record[0],))
            logger.info(['cmd_send_message_1m', ex])
        set_last_message_id(record[3], 0)
        # await dp.bot.send_message(record[3], record[1], disable_web_page_preview=True)

        fb.execsql('update mymtlwalletbot_messages set was_send = 1 where message_id = ?', (record[0],))


def decode_db_effect(row):
    # id, dt, operation, amount1, code1, amount2, code2, from_account, for_account,
    simple_account = row[8][:4] + '..' + row[8][-4:]
    account_link = 'https://stellar.expert/explorer/public/account/' + row[8]
    account_link = f'<a href="{account_link}">{simple_account}</a>'

    op_link = f'<a href="https://stellar.expert/explorer/public/op/{row[0].split("-")[0]}">expert link</a>'
    if row[2] == 'trade':
        return my_gettext(row[9], 'info_trade',
                          (account_link, float2str(row[3]), row[4], float2str(row[5]), row[6], op_link))
    elif row[2] == 'account_debited':
        return my_gettext(row[9], 'info_debit', (account_link, float2str(row[3]), row[4], op_link))
    elif row[2] == 'account_credited':
        return my_gettext(row[9], 'info_credit', (account_link, float2str(row[3]), row[4], op_link))
    else:
        return f'new operation for {account_link} \n\n{op_link}'


async def cmd_send_message_events(dp: Dispatcher):
    for record in fb.execsql(
            'select first 10 o.id, o.dt, o.operation, o.amount1, o.code1, o.amount2, o.code2, o.from_account, o.for_account, m.user_id '
            'from t_operations o join mymtlwalletbot m on m.public_key = o.for_account '
            'and o.id > m.last_event_id order by o.id'):
        try:
            set_last_message_id(record[9], 0)
            await cmd_info_message(record[9], decode_db_effect(record), None)
            set_last_message_id(record[9], 0)
        except Exception as ex:
            logger.info(['cmd_send_message_events', record[0], ex])

        fb.execsql('update mymtlwalletbot set last_event_id = ? where public_key = ? and last_event_id < ?',
                   (record[0], record[8], record[0],))


def scheduler_jobs(scheduler: AsyncIOScheduler, dp):
    scheduler.add_job(cmd_send_message_1m, "interval", seconds=10, args=(dp,))
    scheduler.add_job(cmd_send_message_events, "interval", seconds=8, args=(dp,))
