"""Complete Telegram state after local WebApp sealed-box decryption."""

import redis.asyncio as aioredis
from loguru import logger

from infrastructure.utils.telegram_utils import clear_state
from middleware.notification_activity import complete_notification_flow
from other import faststream_tools
from other.config_reader import config
from other.faststream_tools import broker, clear_pending_sealedbox
from shared.constants import (
    FIELD_STATUS,
    FIELD_USER_ID,
    QUEUE_SEALEDBOX_COMPLETED,
    REDIS_SEALEDBOX_PREFIX,
    STATUS_COMPLETED,
)
from shared.schemas import SealedBoxCompletedMessage


@broker.subscriber(list=QUEUE_SEALEDBOX_COMPLETED)
async def handle_sealedbox_completed(message: SealedBoxCompletedMessage) -> None:
    """Verify completion ownership, clear FSM, and release notifications."""
    app_context = faststream_tools.APP_CONTEXT
    if app_context is None or app_context.dispatcher is None:
        logger.error("Sealed-box completion ignored because AppContext is unavailable")
        return

    redis = aioredis.from_url(config.redis_url)
    try:
        request_key = f"{REDIS_SEALEDBOX_PREFIX}{message.token}"
        raw = await redis.hgetall(request_key)
        data = {
            key.decode() if isinstance(key, bytes) else key: (
                value.decode() if isinstance(value, bytes) else value
            )
            for key, value in raw.items()
        }
        if (
            not data
            or int(data.get(FIELD_USER_ID, 0)) != message.user_id
            or data.get(FIELD_STATUS) != STATUS_COMPLETED
        ):
            logger.warning(
                "Invalid sealed-box completion ignored: user_id={} operation=decrypt result=invalid_completion",
                message.user_id,
            )
            return

        state = app_context.dispatcher.fsm.get_context(
            app_context.bot, message.user_id, message.user_id
        )
        await clear_state(state)
        await complete_notification_flow(app_context, message.user_id)
        await clear_pending_sealedbox(message.user_id, redis_client=redis)
        logger.info("Sealed-box flow completed for user {}", message.user_id)
    finally:
        await redis.aclose()
