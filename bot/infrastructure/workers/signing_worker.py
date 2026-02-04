"""Worker for handling signed transactions from Web App."""

import redis.asyncio as aioredis
from loguru import logger

from other.config_reader import config
from other.faststream_tools import broker, APP_CONTEXT
from other.stellar_tools import async_stellar_send
from keyboards.common_keyboards import get_kb_return
from infrastructure.utils.telegram_utils import send_message
from other.lang_tools import my_gettext

from shared.schemas import TxSignedMessage
from shared.constants import (
    QUEUE_TX_SIGNED,
    REDIS_TX_PREFIX,
    FIELD_SIGNED_XDR,
    FIELD_STATUS,
    STATUS_SIGNED,
)


@broker.subscriber(list=QUEUE_TX_SIGNED)
async def handle_tx_signed(msg: TxSignedMessage) -> None:
    """
    Обрабатывает событие о подписанной транзакции.

    1. Получает signed_xdr из Redis
    2. Отправляет транзакцию в Stellar
    3. Уведомляет пользователя о результате
    4. Удаляет TX из Redis
    """
    try:
        tx_id = msg.tx_id
        user_id = msg.user_id

        logger.info(f"Received tx_signed event for TX {tx_id}, user {user_id}")

        if APP_CONTEXT is None:
            logger.error("APP_CONTEXT is not initialized")
            return

        # Получаем signed_xdr из Redis
        redis_client = aioredis.from_url(config.redis_url)
        try:
            tx_key = f"{REDIS_TX_PREFIX}{tx_id}"
            tx_data = await redis_client.hgetall(tx_key)

            if not tx_data:
                logger.error(f"TX {tx_id}: not found in Redis")
                return

            # Decode bytes to strings
            tx_data = {k.decode(): v.decode() for k, v in tx_data.items()}

            signed_xdr = tx_data.get(FIELD_SIGNED_XDR)
            if not signed_xdr:
                logger.error(f"TX {tx_id}: signed_xdr not found")
                return

            status = tx_data.get(FIELD_STATUS)
            if status != STATUS_SIGNED:
                logger.warning(f"TX {tx_id}: unexpected status {status}")

            # Отправляем в Stellar
            try:
                result = await async_stellar_send(signed_xdr)
                successful = result.get("successful", False)

                # Уведомляем пользователя
                db_pool = APP_CONTEXT.db_pool
                async with db_pool.get_session() as session:
                    if successful:
                        message = my_gettext(user_id, 'transaction_success', app_context=APP_CONTEXT)
                    else:
                        error_msg = result.get("error", "Unknown error")
                        message = my_gettext(user_id, 'transaction_error', app_context=APP_CONTEXT).format(error=error_msg)

                    await send_message(
                        session,
                        user_id,
                        message,
                        reply_markup=get_kb_return(user_id, app_context=APP_CONTEXT),
                        app_context=APP_CONTEXT
                    )

                logger.info(f"TX {tx_id}: submitted to Stellar, successful={successful}")

            except Exception as e:
                logger.exception(f"TX {tx_id}: failed to submit to Stellar: {e}")
                # Уведомляем пользователя об ошибке
                db_pool = APP_CONTEXT.db_pool
                async with db_pool.get_session() as session:
                    message = my_gettext(user_id, 'transaction_error', app_context=APP_CONTEXT).format(error=str(e))
                    await send_message(
                        session,
                        user_id,
                        message,
                        reply_markup=get_kb_return(user_id, app_context=APP_CONTEXT),
                        app_context=APP_CONTEXT
                    )

            # Удаляем TX из Redis
            await redis_client.delete(tx_key)
            logger.info(f"TX {tx_id}: deleted from Redis")

        finally:
            await redis_client.aclose()

    except Exception as e:
        logger.exception(f"Error in handle_tx_signed: {e}")
