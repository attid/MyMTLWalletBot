import asyncio
from datetime import datetime, timedelta

from aiogram import Dispatcher
from aiogram.exceptions import TelegramForbiddenError
from aiogram.fsm.storage.base import StorageKey
from loguru import logger
from sqlalchemy import func, or_

from db.models import TOperations, MyMtlWalletBot, TLOperations, NotificationFilter
from db.db_pool import DatabasePool
from infrastructure.persistence.sqlalchemy_wallet_repository import SqlAlchemyWalletRepository
from infrastructure.utils.async_utils import with_timeout
from infrastructure.utils.common_utils import float2str
from other.global_data import global_data
from other.lang_tools import my_gettext
from other.loguru_tools import safe_catch_async
from routers.start_msg import cmd_info_message


def decode_db_effect(operation: TOperations, decode_for: str, user_id: int):
    """Formats message about operation for sending to user
    
    Args:
        operation: Operation object from database
        decode_for: Public key of wallet for which message is formatted
        user_id: User ID for message localization
    """
    simple_account = operation.for_account[:4] + '..' + operation.for_account[-4:]
    account_link = 'https://viewer.eurmtl.me/account/' + operation.for_account
    account_link = f'<a href="{account_link}">{simple_account}</a>'

    op_link = f'<a href="https://viewer.eurmtl.me/operation/{operation.id.split("-")[0]}">expert link</a>'
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
            decode_for_link = 'https://viewer.eurmtl.me/account/' + decode_for
            decode_for_link = f'<a href="{decode_for_link}">{simple_decode_for}</a>'
            return f"{account_link} set your account {decode_for_link} on his DATA \n\n{op_link}\n\nData Name:\n\n{operation.code1}"
        logger.info(
            f"op type: {operation.operation}, from: {operation.for_account}, {operation.code1}/{operation.code2}")
    else:
        return f'new operation for {account_link} \n\n{op_link}'


@with_timeout(60)
@safe_catch_async
async def fetch_addresses(session_pool: DatabasePool, dp: Dispatcher):
    with session_pool.get_session() as session:
        # Request TLOperations to find accounts with new operations
        tl_query = session.query(TLOperations.account, func.max(TLOperations.id).label('max_id'),
                                 MyMtlWalletBot.user_id) \
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


@safe_catch_async
async def handle_address(tl_result, session_pool: DatabasePool, dp: Dispatcher):
    # 1. Get all data from DB WITHOUT opening long transaction
    with session_pool.get_session() as session:
        logger.info(tl_result.account)
        # Get wallet info
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

    if not operations:
        return

    # 2. Prepare messages and updates
    messages_to_send = []
    last_event_id_to_update = operations[-1].id
    wallet_to_delete = None

    for operation in operations:
        if operation.code1 == 'XLM' and float(operation.amount1) < 0.1:
            continue

        try:
            message_text = decode_db_effect(operation, wallet.public_key, wallet.user_id)
            messages_to_send.append({'user_id': wallet.user_id, 'text': message_text,
                                     'operation_id': operation.id, 'public_key': wallet.public_key,
                                     'wallet_id': wallet.id,
                                     'asset_code': operation.code1, 'amount': float(operation.amount1),
                                     'operation_type': operation.operation})
        except Exception as ex:
            if "Bad Request: chat not found" in str(ex) or isinstance(ex, TelegramForbiddenError):
                wallet_to_delete = {'user_id': wallet.user_id, 'public_key': wallet.public_key}
            logger.info(['handle_address', operation.id, ex])

    # 3. Execute all DB operations in one transaction
    with session_pool.get_session() as session:
        if last_event_id_to_update:
            await asyncio.to_thread(
                session.query(MyMtlWalletBot)
                .filter(MyMtlWalletBot.public_key == wallet.public_key)
                .update, {MyMtlWalletBot.last_event_id: last_event_id_to_update}
            )

        if wallet_to_delete:
            wallet_repo = SqlAlchemyWalletRepository(session)
            await wallet_repo.delete(user_id=wallet_to_delete['user_id'], public_key=wallet_to_delete['public_key'])

        session.commit()

    # 4. Send messages after transaction commit
    for msg in messages_to_send:
        try:
            # Check for notification filters
            with session_pool.get_session() as session:
                user_filters = session.query(NotificationFilter).filter(
                    NotificationFilter.user_id == msg['user_id']).all()

            should_send = True
            for f in user_filters:
                if (f.public_key is None or f.public_key == msg.get('public_key')) and \
                        (f.asset_code is None or f.asset_code == msg.get('asset_code')) and \
                        f.min_amount > msg.get('amount') and \
                        f.operation_type == msg.get('operation_type'):
                    should_send = False
                    break

            if not should_send:
                continue

            fsm_storage_key = StorageKey(bot_id=global_data.bot.id, user_id=msg['user_id'],
                                         chat_id=msg['user_id'])
            await dp.storage.update_data(key=fsm_storage_key, data={'last_message_id': 0})
            await cmd_info_message(None, msg['user_id'], msg['text'],
                                   operation_id=msg.get('operation_id'),
                                   public_key=msg.get('public_key'),
                                   wallet_id=msg.get('wallet_id'))
            await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Failed to send message to {msg['user_id']}: {e}")


@with_timeout(60, kill_on_timeout=False)
@safe_catch_async
async def process_addresses(tl_results, session_pool: DatabasePool, dp: Dispatcher):
    if tl_results is None:
        logger.warning("tl_results is None, skipping processing")
        return
    messages_to_process = tl_results[:20]  # Limit to 10-20 addresses
    tasks = [
        handle_address(tl_result, session_pool, dp)
        for tl_result in messages_to_process
    ]
    await asyncio.gather(*tasks)

    if len(tl_results) > 10:
        logger.info('Ended')


@safe_catch_async
async def events_worker(db_pool: DatabasePool, dp: Dispatcher):
    while True:
        try:
            tl_results = await fetch_addresses(db_pool, dp)
            await process_addresses(tl_results, db_pool, dp)
        except Exception as ex:
            logger.error(['events_worker', ex])
        await asyncio.sleep(10)
