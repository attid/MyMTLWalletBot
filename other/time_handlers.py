import asyncio
from datetime import timedelta, datetime
from functools import wraps
from time import time

from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.storage.base import StorageKey
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import and_, func, or_
from db.models import TOperations, MyMtlWalletBot, MyMtlWalletBotMessages, TLOperations
from db.db_pool import db_pool, DatabasePool
from db.requests import db_delete_wallet, db_delete_wallet_async
from routers.start_msg import cmd_info_message
from other.global_data import global_data
from other.lang_tools import my_gettext
from other.loguru_tools import safe_catch_async
from other.stellar_tools import float2str

class TaskKilled(Exception):
    pass


def kill_task(task):
    task.cancel()


@safe_catch_async
async def task_with_timeout(func, timeout, kill_on_timeout, *args, **kwargs):
    task = asyncio.create_task(func(*args, **kwargs))

    # start_time = datetime.now()

    async def send_update():
        minutes_passed = 0
        while not task.done():
            await asyncio.sleep(60)  # Wait for 1 minute
            minutes_passed += 1
            try:
                await global_data.bot.send_message(
                    chat_id=global_data.admin_id,
                    text=f"Task {func.__name__} has been running for {minutes_passed} minute(s)."
                )
            except:
                pass

    update_task = asyncio.create_task(send_update())

    try:
        result = await asyncio.wait_for(task, timeout=timeout)
        if not update_task.done():
            update_task.cancel()
        return result
    except asyncio.TimeoutError:
        if not update_task.done():
            update_task.cancel()
        raise TaskKilled(f"Task {func.__name__} was timeout")
    finally:
        if kill_on_timeout and not task.done():
            kill_task(task)

        # Send final runtime message
        # total_runtime = (datetime.now() - start_time).total_seconds() / 60
        # try:
        #     await global_data.bot.send_message(
        #         chat_id=global_data.admin_id,
        #         text=f"Task {func.__name__} finished. Total runtime: {total_runtime:.2f} minute(s)."
        #     )
        # except:
        #     pass


def with_timeout(timeout, kill_on_timeout=False):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time()
            task = asyncio.create_task(func(*args, **kwargs))
            minutes_logged = 0

            while not task.done():
                await asyncio.sleep(1)  # Проверяем каждую секунду
                elapsed_time = time() - start_time
                minutes = int(elapsed_time / 60)
                if elapsed_time > timeout and minutes > minutes_logged:
                    logger.warning(f"Функция {func.__name__} работает {minutes} минут")

                    if kill_on_timeout:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            logger.error(f"Задача {func.__name__} была принудительно остановлена")
                        return None
                    else:
                        logger.info(f"Ожидание завершения {func.__name__} после превышения времени выполнения")

                    minutes_logged = minutes

            try:
                result = await task
                return result
            finally:
                if not task.done():
                    logger.warning(f"Задача {func.__name__} все еще выполняется после обработки")
                else:
                    total_minutes = int((time() - start_time) / 60)
                    if total_minutes > 0:
                        logger.info(
                            f"Функция {func.__name__} завершилась, общее время выполнения: {total_minutes} минут")

        return wrapper

    return decorator

@with_timeout(60)
@safe_catch_async
async def cmd_send_message_1m(session_pool, dp: Dispatcher):
    with session_pool.get_session() as session:
        messages = session.query(MyMtlWalletBotMessages).filter(MyMtlWalletBotMessages.was_send == 0).limit(10)
        for message in messages:
            try:
                await cmd_info_message(session, message.user_id, message.user_message, None)
            except Exception as ex:
                if session.query(MyMtlWalletBotMessages).filter_by(message_id=message.message_id).first():
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


@with_timeout(60)
@safe_catch_async
async def fetch_addresses(session_pool, dp: Dispatcher):
    with session_pool.get_session() as session:
        # Запрос TLOperations для поиска аккаунтов с новыми операциями
        tl_query = session.query(TLOperations.account, func.max(TLOperations.id).label('max_id'), MyMtlWalletBot.user_id) \
            .join(MyMtlWalletBot, MyMtlWalletBot.public_key == TLOperations.account) \
            .filter(MyMtlWalletBot.need_delete == 0,
                    MyMtlWalletBot.user_id > 0,
                    TLOperations.dt > datetime.utcnow() - timedelta(minutes=30),
                    TLOperations.id > MyMtlWalletBot.last_event_id
                    ) \
            .group_by(TLOperations.account, MyMtlWalletBot.user_id)

        tl_results = await asyncio.to_thread(tl_query.all)
        if len(tl_results) > 10:
            logger.info(f'founded accounts: {len(tl_results)}')

        return tl_results


@with_timeout(60, kill_on_timeout=False)
@safe_catch_async
async def process_addresses(tl_results, session_pool, dp: Dispatcher):
    if tl_results is None:
        logger.warning("tl_results is None, skipping processing")
        return
    messages_to_process = tl_results[:20]  # Ограничиваем до 10 адресов
    tasks = [
        handle_address(tl_result, session_pool, dp)
        for tl_result in messages_to_process
    ]
    await asyncio.gather(*tasks)

    if len(tl_results) > 10:
        logger.info('Ended')


@safe_catch_async
async def handle_address(tl_result, session_pool, dp: Dispatcher):
    # 1. Получить все данные из БД БЕЗ открытия длительной транзакции
    with session_pool.get_session() as session:
        logger.info(tl_result.account)
        # Получаем информацию о кошельке
        wallet = await asyncio.to_thread(
            session.query(MyMtlWalletBot)
            .filter(MyMtlWalletBot.need_delete == 0,
                    MyMtlWalletBot.user_id == tl_result.user_id,
                    MyMtlWalletBot.public_key == tl_result.account)
            .first
        )
        
        if not wallet:
            return

        operations = await asyncio.to_thread(
            session.query(TOperations)
            .filter(or_(TOperations.for_account == tl_result.account,
                       TOperations.from_account == tl_result.account,
                       TOperations.code2 == tl_result.account),
                    TOperations.id > wallet.last_event_id,
                    TOperations.dt > datetime.utcnow() - timedelta(minutes=30),
                    TOperations.arhived == None)
            .order_by(TOperations.id)
            .all
        )

    # 2. Подготовить сообщения и обновления
    messages_to_send = []
    last_event_id_to_update = None
    wallet_to_delete = None

    for operation in operations:
        if operation.code1 == 'XLM' and float(operation.amount1) < 0.1:
            continue

        last_event_id_to_update = operation.id
        try:
            message_text = decode_db_effect(operation, wallet.public_key, wallet.user_id)
            messages_to_send.append({'user_id': wallet.user_id, 'text': message_text})
        except Exception as ex:
            if "Bad Request: chat not found" in str(ex) or isinstance(ex, TelegramForbiddenError):
                wallet_to_delete = {'user_id': wallet.user_id, 'public_key': wallet.public_key}
            logger.info(['handle_address', operation.id, ex])

    # 3. Выполнить все операции с БД в одной транзакции
    with session_pool.get_session() as session:
        if last_event_id_to_update:
            await asyncio.to_thread(
                session.query(MyMtlWalletBot)
                .filter(MyMtlWalletBot.public_key == wallet.public_key)
                .update, {MyMtlWalletBot.last_event_id: last_event_id_to_update}
            )

        if wallet_to_delete:
            await db_delete_wallet_async(session=session, **wallet_to_delete)

        session.commit()

    # 4. Отправить сообщения после завершения транзакции
    for msg in messages_to_send:
        try:
            fsm_storage_key = StorageKey(bot_id=global_data.bot.id, user_id=msg['user_id'],
                                       chat_id=msg['user_id'])
            await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})
            await cmd_info_message(None, msg['user_id'], msg['text'])
            await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to send message to {msg['user_id']}: {e}")


def decode_db_effect(operation: TOperations, decode_for: str, user_id: int):
    """Форматирует сообщение об операции для отправки пользователю
    
    Args:
        operation: Объект операции из базы данных
        decode_for: Публичный ключ кошелька, для которого форматируется сообщение
        user_id: ID пользователя для локализации сообщений
    """
    simple_account = operation.for_account[:4] + '..' + operation.for_account[-4:]
    account_link = 'https://stellar.expert/explorer/public/account/' + operation.for_account
    account_link = f'<a href="{account_link}">{simple_account}</a>'

    op_link = f'<a href="https://stellar.expert/explorer/public/op/{operation.id.split("-")[0]}">expert link</a>'
    if operation.operation == 'trade':
        return my_gettext(user_id, 'info_trade',
                          (account_link, float2str(operation.amount1), operation.code1,
                           float2str(operation.amount2), operation.code2, op_link))
    elif operation.operation == 'account_debited':
        return my_gettext(user_id, 'info_debit',
                          (account_link, float2str(operation.amount1), operation.code1, op_link))
    elif operation.operation == 'account_credited':
        return my_gettext(user_id, 'info_credit',
                          (account_link, float2str(operation.amount1), operation.code1, op_link))
    elif operation.operation == 'data_removed':
        return f"You remove DATA: \n\n{operation.code1} \n\non {account_link}\n\n{op_link}"
    elif operation.operation in ('data_created', 'data_updated'):
        if operation.for_account == decode_for:
            return f"You added DATA on {account_link}\n\n{op_link}\n\nData:\n\n{operation.code1}\n{operation.code2}"
        if operation.code2 == decode_for:
            simple_decode_for = decode_for[:4] + '..' + decode_for[-4:]
            decode_for_link = 'https://stellar.expert/explorer/public/account/' + decode_for
            decode_for_link = f'<a href="{decode_for_link}">{simple_decode_for}</a>'
            return f"{account_link} set your account {decode_for_link} on his DATA \n\n{op_link}\n\nData Name:\n\n{operation.code1}"
        logger.info(f"op type: {operation.operation}, from: {operation.for_account}, {operation.code1}/{operation.code2}")
    else:
        return f'new operation for {account_link} \n\n{op_link}'


def scheduler_jobs(scheduler: AsyncIOScheduler, db_pool: DatabasePool, dp: Dispatcher):
    scheduler.add_job(cmd_send_message_1m, "interval", seconds=10, args=(db_pool, dp), misfire_grace_time=60)
    # scheduler.add_job(cmd_send_message_events, "interval", seconds=8, args=(db_pool, dp), misfire_grace_time=60)


@safe_catch_async
async def events_worker(db_pool: DatabasePool, dp: Dispatcher):
    while True:
        try:
            tl_results = await fetch_addresses(db_pool, dp)
            await process_addresses(tl_results, db_pool, dp)
        except Exception as ex:
            logger.error(['events_worker', ex])
        await asyncio.sleep(10)


async def test():
    dp = None  # Создаем переменную dp
    tl_results = await fetch_addresses(db_pool, dp)
    await process_addresses(tl_results, db_pool, dp)
    print("Разделение функции завершено.")


if __name__ == '__main__':
    asyncio.run(test())
    pass
