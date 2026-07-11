"""Opt-in parity checks for notification Redis Lua scripts.

Set ``REDIS_URL`` to a disposable Redis database before running this external
suite.  The test uses a unique key prefix and removes all keys it creates.
"""

import os
import uuid

import pytest
from redis.asyncio import Redis

from core.models.blockchain_notification import BlockchainNotification
from infrastructure.services.notification_redis_store import NotificationRedisStore


pytestmark = pytest.mark.external


@pytest.fixture
async def redis_store() -> NotificationRedisStore:
    redis_url = os.getenv("REDIS_URL")
    if redis_url is None:
        pytest.skip("set REDIS_URL to run real Redis notification-store parity tests")
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        await redis.ping()
    except OSError as error:
        await redis.aclose()
        pytest.skip(f"configured REDIS_URL is unavailable: {error}")
    prefix = f"notification-test-{uuid.uuid4()}"
    store = NotificationRedisStore(
        redis,
        hold_seconds=120,
        lock_ttl_seconds=30,
        key_prefix=f"{prefix}:",
    )
    try:
        yield store
    finally:
        keys = await redis.keys(f"{prefix}:*")
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


def _notification(transaction_hash: str = "tx-1") -> BlockchainNotification:
    return BlockchainNotification(
        notification_id=f"notification-{transaction_hash}",
        user_id=42,
        event_type="payment",
        text="First payment",
        created_at=1_720_000_000,
        transaction_hash=transaction_hash,
        event_index=0,
        data={"amount": "10.5"},
    )


@pytest.mark.asyncio
async def test_real_redis_lua_paths_preserve_due_and_pending_invariants(
    redis_store: NotificationRedisStore,
) -> None:
    redis = redis_store._redis
    hold_until = await redis_store.touch(42, now=1_000)
    assert hold_until == 1_120
    assert await redis.zscore(redis_store._due_key(), "42") == 1_120
    assert (
        await redis_store.release_due_hold_if_unchanged(42, hold_until - 1, now=1_120)
        is False
    )
    assert await redis_store.hold_until(42) == hold_until
    assert (
        await redis_store.release_due_hold_if_unchanged(42, hold_until, now=1_120)
        is True
    )

    expired_hold_until = await redis_store.touch(42, now=1_000)
    pending_event = _notification("tx-pending")
    assert (
        await redis_store.claim_accept(42, pending_event, now=expired_hold_until)
        == "direct"
    )
    assert (
        await redis_store.release_due_hold_if_unchanged(
            42, expired_hold_until, now=1_130
        )
        is True
    )
    assert await redis_store.pending_count(42) == 1
    assert await redis_store.due_users(now=1_129) == []
    assert await redis_store.due_users(now=1_130) == [42]

    assert await redis_store.acquire_lock(42, "owner-token") is True
    assert await redis_store.release_lock(42, "wrong-token") is False
    assert await redis_store.renew_lock(42, "wrong-token") is False
    assert await redis_store.renew_lock(42, "owner-token") is True
    assert await redis_store.acquire_lock(42, "other-token") is False
    assert await redis_store.release_lock(42, "owner-token") is True
    assert await redis_store.acquire_lock(42, "owner-token") is True
    assert (
        await redis_store.acknowledge_if_lock_owned(42, pending_event, "owner-token")
        is True
    )
    assert await redis_store.release_lock(42, "owner-token") is True

    await redis.zadd(redis_store._due_key(), {"1": 1_000, "42": 1_000})
    await redis.set(redis_store._hold_key(42), 1_120)

    assert await redis_store.due_users(now=1_000) == []
    assert await redis.zscore(redis_store._due_key(), "1") is None
    assert await redis.zscore(redis_store._due_key(), "42") == 1_120
    assert await redis_store.release_hold_if_unchanged(42, 1_120, now=1_120) is True

    event = _notification()
    assert await redis_store.claim_accept(42, event, now=1_000) == "direct"
    assert await redis_store.claim_accept(42, event, now=1_000) == "duplicate"
    assert await redis_store.due_users(now=1_000) == [42]
    assert await redis_store.peek(42) == event
    assert (
        await redis_store.acknowledge_if_lock_owned(42, event, "owner-token") is False
    )
    assert await redis_store.acquire_lock(42, "owner-token") is True
    assert await redis_store.acknowledge_if_lock_owned(42, event, "owner-token") is True

    stale_event = _notification("tx-stale")
    assert await redis_store.claim_accept(42, stale_event, now=1_000) == "direct"
    assert await redis_store.release_lock(42, "owner-token") is True
    assert await redis_store.acquire_lock(42, "new-owner-token") is True
    assert (
        await redis_store.acknowledge_if_lock_owned(42, stale_event, "owner-token")
        is False
    )
    assert await redis_store.peek(42) == stale_event
    assert (
        await redis_store.acknowledge_if_lock_owned(42, stale_event, "new-owner-token")
        is True
    )

    await redis_store.touch(42, now=1_000)
    queued_event = _notification("tx-2")
    assert await redis_store.claim_accept(42, queued_event, now=1_000) == "queued"
    assert (
        await redis_store.acknowledge_if_lock_owned(42, queued_event, "new-owner-token")
        is True
    )
    assert not await redis.sismember(
        redis_store._pending_id_key(42), event.idempotency_key
    )


@pytest.mark.asyncio
async def test_real_redis_lua_due_scan_cleans_a_stale_prefix_without_starving_due_users(
    redis_store: NotificationRedisStore,
) -> None:
    redis = redis_store._redis
    await redis.zadd(
        redis_store._due_key(), {str(user_id): 1_000 for user_id in range(1, 8)}
    )
    await redis.zadd(redis_store._due_key(), {"90": 1_000, "91": 1_000})
    await redis.set(redis_store._hold_key(90), 1_000)
    await redis.set(redis_store._hold_key(91), 1_000)

    assert await redis_store.due_users(now=1_000, limit=2) == [90, 91]
    assert await redis.zscore(redis_store._due_key(), "1") is None
    assert await redis.zscore(redis_store._due_key(), "7") is None
