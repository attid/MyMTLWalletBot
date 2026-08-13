"""Complete Telegram state after local WebApp sealed-box decryption."""

import base64

import redis.asyncio as aioredis
from aiogram.types import BufferedInputFile
from loguru import logger

from keyboards.common_keyboards import get_kb_return
from infrastructure.utils.telegram_utils import clear_state
from middleware.notification_activity import complete_notification_flow
from other import faststream_tools
from other.config_reader import config
from other.faststream_tools import broker, clear_pending_sealedbox
from shared.constants import (
    FIELD_STATUS,
    FIELD_SEALEDBOX_OUTPUT_FILENAME,
    FIELD_SEALEDBOX_PLAINTEXT,
    FIELD_USER_ID,
    QUEUE_SEALEDBOX_COMPLETED,
    QUEUE_SEALEDBOX_RELAY,
    REDIS_SEALEDBOX_PREFIX,
    REDIS_SEALEDBOX_USER_PREFIX,
    STATUS_COMPLETED,
    STATUS_RELAY_PENDING,
    SEALEDBOX_MAX_PLAINTEXT_BYTES,
)
from shared.schemas import SealedBoxCompletedMessage, SealedBoxRelayMessage


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


@broker.subscriber(list=QUEUE_SEALEDBOX_RELAY)
async def handle_sealedbox_relay(message: SealedBoxRelayMessage) -> None:
    """Send owner-approved plaintext to Telegram, then remove every copy."""
    app_context = faststream_tools.APP_CONTEXT
    if app_context is None or app_context.dispatcher is None:
        logger.error("Sealed-box relay ignored because AppContext is unavailable")
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
            or data.get(FIELD_STATUS) != STATUS_RELAY_PENDING
        ):
            logger.warning(
                "Invalid sealed-box relay ignored: user_id={} operation=relay result=invalid_request",
                message.user_id,
            )
            return
        try:
            plaintext = base64.b64decode(
                data.get(FIELD_SEALEDBOX_PLAINTEXT, ""), validate=True
            )
        except (ValueError, base64.binascii.Error):
            plaintext = b""
        if not plaintext or len(plaintext) > SEALEDBOX_MAX_PLAINTEXT_BYTES:
            logger.warning(
                "Invalid sealed-box relay ignored: user_id={} operation=relay result=invalid_payload",
                message.user_id,
            )
            return

        filename = data.get(FIELD_SEALEDBOX_OUTPUT_FILENAME, "").strip()
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        filename = filename or "sealedbox-output.bin"
        await app_context.bot.send_document(
            message.user_id,
            BufferedInputFile(plaintext, filename=filename[:180]),
            reply_markup=get_kb_return(message.user_id, app_context=app_context),
        )
        state = app_context.dispatcher.fsm.get_context(
            app_context.bot, message.user_id, message.user_id
        )
        await clear_state(state)
        await complete_notification_flow(app_context, message.user_id)
        user_key = f"{REDIS_SEALEDBOX_USER_PREFIX}{message.user_id}"
        active_token = await redis.get(user_key)
        if isinstance(active_token, bytes):
            active_token = active_token.decode()
        await redis.delete(request_key)
        if active_token == message.token:
            await redis.delete(user_key)
        logger.info("Sealed-box relay delivered for user {}", message.user_id)
    finally:
        await redis.aclose()
