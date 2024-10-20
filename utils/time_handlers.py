import asyncio
from datetime import timedelta, datetime
from functools import wraps

from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.storage.base import StorageKey
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import and_, func
from sqlalchemy.orm import sessionmaker
from db.models import TOperations, MyMtlWalletBot, MyMtlWalletBotMessages, TLOperations
from db.quik_pool import quik_pool
from db.requests import db_delete_wallet
from routers.start_msg import cmd_info_message
from utils.global_data import global_data
from utils.lang_utils import my_gettext
from utils.stellar_utils import float2str


class TaskKilled(Exception):
    pass


def kill_task(task):
    task.cancel()


async def task_with_timeout(func, timeout, kill_on_timeout, *args, **kwargs):
    loop = asyncio.get_event_loop()
    task = loop.create_task(func(*args, **kwargs))
    try:
        return await asyncio.wait_for(task, timeout=timeout)
    except asyncio.TimeoutError:
        # dp:Dispatcher = next((arg for arg in args if isinstance(arg, Dispatcher)), None)
        try:
            await global_data.bot.send_message(chat_id=global_data.admin_id,
                                               text=f"Task {func.__name__} exceeded timeout of {timeout} seconds.")
        except:
            pass

        if kill_on_timeout:
            logger.warning(f"Task {func.__name__} exceeded timeout of {timeout} seconds. Killing the task.")
            kill_task(task)
            raise TaskKilled(f"Task {func.__name__} was killed due to timeout")
        else:
            logger.warning(f"Task {func.__name__} exceeded timeout of {timeout} seconds. Continuing execution.")
    finally:
        if kill_on_timeout and not task.done():
            kill_task(task)


def with_timeout(timeout, kill_on_timeout=False):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await task_with_timeout(func, timeout, kill_on_timeout, *args, **kwargs)
            except TaskKilled as e:
                logger.error(str(e))
                # Здесь вы можете добавить дополнительную обработку "убитой" задачи
                return None

        return wrapper

    return decorator


@with_timeout(60)
async def cmd_send_message_1m(session_pool, dp: Dispatcher):
    with session_pool() as session:
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
            fsm_storage_key = StorageKey(bot_id=global_data.bot.id, user_id=message.user_id, chat_id=message.user_id)
            await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})
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


@with_timeout(60)
async def cmd_send_message_events(session_pool, dp: Dispatcher):
    with session_pool() as session:
        # First, query TLOperations to find accounts with new operations
        tl_query = session.query(TLOperations.account, TLOperations.id.label('max_id')) \
            .join(MyMtlWalletBot, MyMtlWalletBot.public_key == TLOperations.account) \
            .filter(MyMtlWalletBot.need_delete == 0,
                    MyMtlWalletBot.user_id > 0,
                    TLOperations.dt > datetime.utcnow() - timedelta(minutes=30),
                    TLOperations.id > MyMtlWalletBot.last_event_id
                    )

        # print(tl_query)

        tl_results = await asyncio.to_thread(tl_query.all)
        # logger.info(f'founded accounts: {len(tl_results)}')

        for tl_result in tl_results:
            logger.info(tl_result.account)
            # For each account with new operations, query TOperations
            query = session.query(TOperations.id, TOperations.dt, TOperations.operation, TOperations.amount1,
                                  TOperations.code1, TOperations.amount2, TOperations.code2, TOperations.from_account,
                                  TOperations.for_account, MyMtlWalletBot.user_id) \
                .join(MyMtlWalletBot, MyMtlWalletBot.public_key == TOperations.for_account) \
                .filter(MyMtlWalletBot.need_delete == 0, MyMtlWalletBot.user_id > 0,
                        TOperations.id > MyMtlWalletBot.last_event_id,
                        TOperations.for_account == tl_result.account,
                        TOperations.dt > datetime.utcnow() - timedelta(minutes=30),
                        TOperations.arhived == None) \
                .order_by(TOperations.id) \
                .limit(10)

            # records = query.all()
            records = await asyncio.to_thread(query.all)

            for record in records:
                # Обновление last_event_id перед проверкой
                session.query(MyMtlWalletBot) \
                    .filter(MyMtlWalletBot.public_key == record.for_account) \
                    .update({MyMtlWalletBot.last_event_id: record.id})

                try:
                    if record.code1 == 'XLM' and float(record.amount1) < 0.1:
                        continue

                    fsm_storage_key = StorageKey(bot_id=global_data.bot.id, user_id=record.user_id,
                                                 chat_id=record.user_id)
                    await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})
                    await cmd_info_message(session, record.user_id, decode_db_effect(record))
                    await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})
                except TelegramBadRequest as ex:
                    if "Bad Request: chat not found" in str(ex):
                        db_delete_wallet(session=session, user_id=record.user_id, public_key=record.for_account)
                        logger.info(['cmd_send_message_events', record.id, 'wallet was deleted'])
                    else:
                        logger.info(['cmd_send_message_events 01', record.id, ex])
                except TelegramForbiddenError:
                    db_delete_wallet(session=session, user_id=record.user_id, public_key=record.for_account)
                    logger.info(['cmd_send_message_events', record.id, 'Forbidden wallet was deleted'])
                except Exception as ex:
                    logger.info(['cmd_send_message_events', record.id, ex])

            session.commit()


def scheduler_jobs(scheduler: AsyncIOScheduler, db_pool: sessionmaker, dp: Dispatcher):
    scheduler.add_job(cmd_send_message_1m, "interval", seconds=10, args=(db_pool, dp), misfire_grace_time=60)
    scheduler.add_job(cmd_send_message_events, "interval", seconds=8, args=(db_pool, dp), misfire_grace_time=60)


async def test():
    a = await cmd_send_message_events(quik_pool, None)
    print(a)


if __name__ == '__main__':
    asyncio.run(test())
    pass
