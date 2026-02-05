"""Worker for handling signed transactions from Web App."""

import jsonpickle  # type: ignore
import redis.asyncio as aioredis
from loguru import logger

from other.config_reader import config
from other import faststream_tools
from other.faststream_tools import broker

from shared.schemas import TxSignedMessage
from shared.constants import (
    QUEUE_TX_SIGNED,
    REDIS_TX_PREFIX,
    FIELD_SIGNED_XDR,
    FIELD_STATUS,
    FIELD_FSM_AFTER_SEND,
    FIELD_SUCCESS_MSG,
    STATUS_SIGNED,
)


@broker.subscriber(list=QUEUE_TX_SIGNED)
async def handle_tx_signed(msg: TxSignedMessage) -> None:
    """
    Обрабатывает событие о подписанной транзакции.

    1. Получает signed_xdr из Redis
    2. Отправляет транзакцию в Stellar
    3. Вызывает fsm_after_send callback (если есть)
    4. Уведомляет пользователя о результате
    5. Удаляет TX из Redis
    """
    try:
        tx_id = msg.tx_id
        user_id = msg.user_id

        logger.info(f"Received tx_signed event for TX {tx_id}, user {user_id}")

        if faststream_tools.APP_CONTEXT is None:
            logger.error("APP_CONTEXT is not initialized")
            return

        # Получаем данные из Redis
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

            # Извлекаем fsm_after_send и success_msg
            fsm_after_send_pickled = tx_data.get(FIELD_FSM_AFTER_SEND)
            success_msg = tx_data.get(FIELD_SUCCESS_MSG)

            # Отправляем в Stellar через единую функцию
            from routers.sign import submit_signed_xdr

            db_pool = faststream_tools.APP_CONTEXT.db_pool
            async with db_pool.get_session() as session:
                result = await submit_signed_xdr(
                    session,
                    user_id,
                    signed_xdr,
                    success_msg=success_msg,
                    app_context=faststream_tools.APP_CONTEXT,
                )

                successful = result.get("successful", False)
                logger.info(f"TX {tx_id}: submitted to Stellar, successful={successful}")

                # Вызываем fsm_after_send callback если транзакция успешна
                if successful and fsm_after_send_pickled:
                    try:
                        fsm_after_send = jsonpickle.loads(fsm_after_send_pickled)
                        logger.info(f"TX {tx_id}: calling fsm_after_send callback")

                        # Получаем FSM state для пользователя
                        bot = faststream_tools.APP_CONTEXT.bot
                        dispatcher = faststream_tools.APP_CONTEXT.dispatcher
                        assert dispatcher is not None, "Dispatcher must be initialized"
                        state = dispatcher.fsm.get_context(bot, user_id, user_id)

                        await fsm_after_send(session, user_id, state)
                        logger.info(f"TX {tx_id}: fsm_after_send callback completed")
                    except Exception as e:
                        logger.exception(f"TX {tx_id}: error in fsm_after_send: {e}")

            # Удаляем TX из Redis
            await redis_client.delete(tx_key)
            logger.info(f"TX {tx_id}: deleted from Redis")

        finally:
            await redis_client.aclose()

    except Exception as e:
        logger.exception(f"Error in handle_tx_signed: {e}")
