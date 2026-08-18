import base64

import fakeredis.aioredis
import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from unittest.mock import AsyncMock, MagicMock, patch

from other.faststream_tools import (
    clear_pending_sealedbox,
    publish_pending_sealedbox,
)
from shared.constants import (
    FIELD_SEALEDBOX_CIPHERTEXT,
    FIELD_SEALEDBOX_OUTPUT_FILENAME,
    FIELD_SEALEDBOX_PLAINTEXT,
    FIELD_USER_ID,
    REDIS_SEALEDBOX_PREFIX,
    REDIS_SEALEDBOX_USER_PREFIX,
    FIELD_STATUS,
    STATUS_COMPLETED,
    STATUS_RELAY_PENDING,
)
from shared.schemas import SealedBoxCompletedMessage, SealedBoxRelayMessage


@pytest.mark.asyncio
async def test_publish_stores_only_ciphertext_and_safe_metadata() -> None:
    redis = fakeredis.aioredis.FakeRedis()

    token = await publish_pending_sealedbox(
        user_id=42,
        wallet_address="GACTIVE",
        ciphertext=b"cipher bytes",
        output_filename="report.pdf",
        redis_client=redis,
    )

    values = await redis.hgetall(f"{REDIS_SEALEDBOX_PREFIX}{token}")
    assert values[FIELD_USER_ID.encode()] == b"42"
    assert (
        base64.b64decode(values[FIELD_SEALEDBOX_CIPHERTEXT.encode()]) == b"cipher bytes"
    )
    assert values[FIELD_SEALEDBOX_OUTPUT_FILENAME.encode()] == b"report.pdf"
    serialized = b" ".join(values.keys()) + b" " + b" ".join(values.values())
    assert b"secret_key" not in serialized
    assert b"plaintext" not in serialized
    assert await redis.ttl(f"{REDIS_SEALEDBOX_PREFIX}{token}") > 0
    await redis.aclose()


@pytest.mark.asyncio
async def test_new_request_replaces_previous_request_for_user() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    first = await publish_pending_sealedbox(
        user_id=42,
        wallet_address="GACTIVE",
        ciphertext=b"first",
        output_filename="first.bin",
        redis_client=redis,
    )

    second = await publish_pending_sealedbox(
        user_id=42,
        wallet_address="GACTIVE",
        ciphertext=b"second",
        output_filename="second.bin",
        redis_client=redis,
    )

    assert not await redis.exists(f"{REDIS_SEALEDBOX_PREFIX}{first}")
    assert await redis.exists(f"{REDIS_SEALEDBOX_PREFIX}{second}")
    assert await redis.get(f"{REDIS_SEALEDBOX_USER_PREFIX}42") == second.encode()
    await redis.aclose()


@pytest.mark.asyncio
async def test_clear_removes_request_and_user_pointer() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    token = await publish_pending_sealedbox(
        user_id=42,
        wallet_address="GACTIVE",
        ciphertext=b"cipher",
        output_filename="file.bin",
        redis_client=redis,
    )

    assert await clear_pending_sealedbox(42, redis_client=redis)

    assert not await redis.exists(f"{REDIS_SEALEDBOX_PREFIX}{token}")
    assert not await redis.exists(f"{REDIS_SEALEDBOX_USER_PREFIX}42")
    await redis.aclose()


@pytest.mark.asyncio
async def test_completion_worker_clears_fsm_and_releases_notifications() -> None:
    from infrastructure.workers import sealedbox_worker
    from other import faststream_tools

    redis = fakeredis.aioredis.FakeRedis()
    token = await publish_pending_sealedbox(
        user_id=42,
        wallet_address="GACTIVE",
        ciphertext=b"cipher",
        output_filename="file.bin",
        redis_client=redis,
    )
    await redis.hset(f"{REDIS_SEALEDBOX_PREFIX}{token}", FIELD_STATUS, STATUS_COMPLETED)
    state = AsyncMock()
    app_context = MagicMock()
    app_context.bot = MagicMock()
    app_context.dispatcher.fsm.get_context.return_value = state
    old_context = faststream_tools.APP_CONTEXT
    faststream_tools.APP_CONTEXT = app_context
    try:
        with (
            patch.object(
                sealedbox_worker.aioredis,
                "from_url",
                return_value=redis,
            ),
            patch.object(sealedbox_worker, "clear_state", AsyncMock()) as clear,
            patch.object(
                sealedbox_worker, "complete_current_notification_flow", AsyncMock()
            ) as complete,
        ):
            await sealedbox_worker.handle_sealedbox_completed(
                SealedBoxCompletedMessage(token=token, user_id=42)
            )

        clear.assert_awaited_once_with(state)
        complete.assert_awaited_once_with(app_context, 42)
        assert not await redis.exists(f"{REDIS_SEALEDBOX_PREFIX}{token}")
    finally:
        faststream_tools.APP_CONTEXT = old_context
        await redis.aclose()


@pytest.mark.asyncio
async def test_relay_worker_sends_plaintext_and_clears_request() -> None:
    from infrastructure.workers import sealedbox_worker
    from other import faststream_tools

    redis = fakeredis.aioredis.FakeRedis()
    token = await publish_pending_sealedbox(
        user_id=42,
        wallet_address="GACTIVE",
        ciphertext=b"cipher",
        output_filename="report.pdf",
        redis_client=redis,
    )
    await redis.hset(
        f"{REDIS_SEALEDBOX_PREFIX}{token}",
        mapping={
            FIELD_STATUS: STATUS_RELAY_PENDING,
            FIELD_SEALEDBOX_PLAINTEXT: base64.b64encode(b"relay <text>").decode(),
        },
    )
    app_context = MagicMock()
    app_context.bot.id = 1
    app_context.bot.send_document = AsyncMock(return_value=MagicMock(message_id=91))
    app_context.localization_service.get_text.return_value = "Home"
    app_context.notification_badge_service = None
    app_context.dispatcher = Dispatcher(storage=MemoryStorage())
    old_context = faststream_tools.APP_CONTEXT
    faststream_tools.APP_CONTEXT = app_context
    try:
        with (
            patch.object(sealedbox_worker.aioredis, "from_url", return_value=redis),
            patch.object(sealedbox_worker, "clear_state", AsyncMock()) as clear,
            patch.object(
                sealedbox_worker, "complete_current_notification_flow", AsyncMock()
            ) as complete,
        ):
            await sealedbox_worker.handle_sealedbox_relay(
                SealedBoxRelayMessage(token=token, user_id=42)
            )

        sent_document = app_context.bot.send_document.await_args.args[1]
        assert sent_document.data == b"relay <text>"
        assert sent_document.filename == "report.pdf"
        assert app_context.bot.send_document.await_args.kwargs["caption"] == (
            "<code>relay &lt;text&gt;</code>"
        )
        clear.assert_awaited_once()
        complete.assert_awaited_once_with(app_context, 42)
        key = StorageKey(bot_id=1, chat_id=42, user_id=42)
        assert (await app_context.dispatcher.storage.get_data(key))[
            "last_message_id"
        ] == 91
        assert not await redis.exists(f"{REDIS_SEALEDBOX_PREFIX}{token}")
    finally:
        faststream_tools.APP_CONTEXT = old_context
        await redis.aclose()
