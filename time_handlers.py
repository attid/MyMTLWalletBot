from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import and_
from sqlalchemy.orm import Session

from db.models import TOperations, MyMtlWalletBot, MyMtlWalletBotMessages
from routers.start_msg import cmd_info_message
from utils.lang_utils import set_last_message_id, my_gettext
from utils.stellar_utils import float2str


async def cmd_send_message_1m(session: Session):
    messages = session.query(MyMtlWalletBotMessages).filter(MyMtlWalletBotMessages.was_send == 0).limit(10)
    for message in messages:
        try:
            await cmd_info_message(session, message.user_id, message.user_message, None)
        except Exception as ex:
            session.query(MyMtlWalletBotMessages).filter(
                MyMtlWalletBotMessages.message_id == message.message_id).update(
                {MyMtlWalletBotMessages.was_send: 2})
            session.commit()
            logger.info(['cmd_send_message_1m', ex])
        set_last_message_id(session, message.user_id, 0)
        # await dp.bot.send_message(record[3], record[1], disable_web_page_preview=True)

        session.query(MyMtlWalletBotMessages).filter(
            and_(MyMtlWalletBotMessages.message_id == message.message_id)).update(
            {MyMtlWalletBotMessages.was_send: 1})
        session.commit()


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


async def cmd_send_message_events(session: Session):
    records = session.query(TOperations.id, TOperations.dt, TOperations.operation, TOperations.amount1,
                            TOperations.code1, TOperations.amount2, TOperations.code2, TOperations.from_account,
                            TOperations.for_account, MyMtlWalletBot.user_id) \
        .filter(MyMtlWalletBot.public_key == TOperations.for_account,
                TOperations.id > MyMtlWalletBot.last_event_id) \
        .order_by(TOperations.id) \
        .limit(10) \
        .all()

    for record in records:
        try:
            await set_last_message_id(session,record.user_id, 0)
            await cmd_info_message(session, record.user_id, decode_db_effect(record), None)
            await set_last_message_id(session,record.user_id, 0)
        except Exception as ex:
            logger.info(['cmd_send_message_events', record.id, ex])

        # Update last_event_id for all users whose public_key matches record.for_account and last_event_id is smaller than record.id
        session.query(MyMtlWalletBot) \
            .filter(MyMtlWalletBot.public_key == record.for_account, MyMtlWalletBot.last_event_id < record.id) \
            .update({MyMtlWalletBot.last_event_id: record.id})
        session.commit()


def scheduler_jobs(scheduler: AsyncIOScheduler, dp):
    scheduler.add_job(cmd_send_message_1m, "interval", seconds=10, args=(dp,))
    scheduler.add_job(cmd_send_message_events, "interval", seconds=8, args=(dp,))
