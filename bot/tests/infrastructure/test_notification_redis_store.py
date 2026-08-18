import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from redis.exceptions import ResponseError

from core.models.blockchain_notification import BlockchainNotification
from infrastructure.services.notification_redis_store import NotificationRedisStore


@pytest.fixture
async def redis_store() -> NotificationRedisStore:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    yield store
    await redis.aclose()


def notification(transaction_hash: str, text: str) -> BlockchainNotification:
    return BlockchainNotification(
        notification_id=f"notification-{transaction_hash}",
        user_id=42,
        event_type="payment",
        text=text,
        created_at=1_720_000_000,
        transaction_hash=transaction_hash,
        event_index=0,
        data={"amount": "10.5", "is_incoming": True},
    )


def test_notification_serialization_is_canonical_and_uses_stable_primitives():
    event = notification("tx-1", "First payment")

    assert event.to_json() == (
        '{"created_at":1720000000,"data":{"amount":"10.5",'
        '"is_incoming":true},"event_index":0,"event_type":"payment",'
        '"idempotency_key":"tx-1:payment:0:42",'
        '"notification_id":"notification-tx-1","text":"First payment",'
        '"transaction_hash":"tx-1","user_id":42}'
    )
    assert BlockchainNotification.from_json(event.to_json()) == event


def test_notification_rejects_a_serialized_idempotency_key_that_does_not_match_event_identity():
    event = notification("tx-1", "First payment")

    with pytest.raises(ValueError, match="idempotency_key"):
        BlockchainNotification.from_json(
            event.to_json().replace("tx-1:payment:0:42", "incorrect-key")
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_notification_rejects_non_finite_data_floats(value: float):
    with pytest.raises(ValueError, match="finite"):
        replace(notification("tx-1", "First payment"), data={"amount": value})


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_notification_rejects_non_finite_floats_during_json_parse(value: str):
    event = notification("tx-1", "First payment")

    with pytest.raises(ValueError, match="non-finite"):
        BlockchainNotification.from_json(event.to_json().replace('"10.5"', value))


def test_notification_data_is_an_immutable_mapping_copy():
    original_data = {"amount": "10.5"}
    event = replace(notification("tx-1", "First payment"), data=original_data)

    original_data["amount"] = "999"

    assert isinstance(event.data, MappingProxyType)
    assert event.data == {"amount": "10.5"}
    with pytest.raises(TypeError):
        event.data["amount"] = "0"  # type: ignore[index]


@pytest.mark.parametrize(
    ("field", "value"),
    [("event_type", 1), ("text", 1), ("data", None)],
)
def test_notification_requires_string_event_content_and_primitive_data_object(
    field: str, value: object
):
    with pytest.raises(TypeError):
        replace(notification("tx-1", "First payment"), **{field: value})


@pytest.mark.asyncio
async def test_touch_creates_and_extends_absolute_hold(
    redis_store: NotificationRedisStore,
):
    assert await redis_store.touch(42, now=1_000) == 1_120
    assert await redis_store.hold_until(42) == 1_120

    assert await redis_store.touch(42, now=1_050) == 1_170
    assert await redis_store.hold_until(42) == 1_170


@pytest.mark.asyncio
async def test_touch_with_generation_returns_one_atomic_hold_snapshot(
    redis_store: NotificationRedisStore,
):
    touched = await redis_store.touch_with_generation(42, now=1_000)

    assert touched == await redis_store.hold_snapshot(42)
    assert touched[0] == 1_120
    assert touched[1] > 0


@pytest.mark.asyncio
async def test_same_second_touch_has_a_distinct_flow_generation(
    redis_store: NotificationRedisStore,
):
    await redis_store.touch(42, now=1_000)
    first_snapshot = await redis_store.hold_snapshot(42)
    assert first_snapshot is not None

    await redis_store.touch(42, now=1_000)

    assert (
        await redis_store.release_hold_generation_if_unchanged(
            42, first_snapshot[1], now=1_000
        )
        is False
    )
    assert await redis_store.hold_until(42) == 1_120


@pytest.mark.asyncio
async def test_same_second_generation_fencing_works_without_lua():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    redis.eval = AsyncMock(side_effect=ResponseError("unknown command 'eval'"))
    try:
        await store.touch(42, now=1_000)
        first_snapshot = await store.hold_snapshot(42)
        assert first_snapshot is not None
        await store.touch(42, now=1_000)
        second_snapshot = await store.hold_snapshot(42)
        assert second_snapshot is not None

        assert (
            await store.release_hold_generation_if_unchanged(
                42, first_snapshot[1], now=1_000
            )
            is False
        )
        assert (
            await store.release_hold_generation_if_unchanged(
                42, second_snapshot[1], now=1_000
            )
            is True
        )
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_release_removes_hold_and_due_schedule(
    redis_store: NotificationRedisStore,
):
    await redis_store.touch(42, now=1_000)

    await redis_store.release(42)

    assert await redis_store.hold_until(42) is None
    assert await redis_store.due_users(now=2_000) == []


@pytest.mark.asyncio
async def test_release_due_hold_if_unchanged_removes_matching_hold_and_schedule(
    redis_store: NotificationRedisStore,
):
    expected_hold_until = await redis_store.touch(42, now=1_000)

    assert (
        await redis_store.release_due_hold_if_unchanged(
            42, expected_hold_until, now=1_120
        )
        is True
    )
    assert await redis_store.hold_until(42) is None
    assert await redis_store.due_users(now=2_000) == []


@pytest.mark.asyncio
async def test_release_due_hold_if_unchanged_rejects_mismatched_deadline(
    redis_store: NotificationRedisStore,
):
    expected_hold_until = await redis_store.touch(42, now=1_000)

    assert (
        await redis_store.release_due_hold_if_unchanged(
            42, expected_hold_until - 1, now=1_120
        )
        is False
    )
    assert await redis_store.hold_until(42) == expected_hold_until
    assert await redis_store.due_users(now=expected_hold_until) == [42]


@pytest.mark.asyncio
async def test_release_due_hold_if_unchanged_preserves_a_concurrently_renewed_hold(
    redis_store: NotificationRedisStore,
):
    stale_hold_until = await redis_store.touch(42, now=1_000)
    renewed_hold_until = await redis_store.touch(42, now=1_050)

    assert (
        await redis_store.release_due_hold_if_unchanged(
            42, stale_hold_until, now=stale_hold_until
        )
        is False
    )
    assert await redis_store.hold_until(42) == renewed_hold_until
    assert await redis_store.due_users(now=stale_hold_until) == []
    assert await redis_store.due_users(now=renewed_hold_until) == [42]


@pytest.mark.asyncio
async def test_release_due_hold_if_unchanged_keeps_pending_work_due_immediately(
    redis_store: NotificationRedisStore,
):
    expired_hold_until = await redis_store.touch(42, now=1_000)
    event = notification("tx-1", "First payment")

    assert await redis_store.claim_accept(42, event, now=expired_hold_until) == "direct"
    assert (
        await redis_store.release_due_hold_if_unchanged(
            42, expired_hold_until, now=1_130
        )
        is True
    )

    assert await redis_store.hold_until(42) is None
    assert await redis_store.pending_count(42) == 1
    assert await redis_store.due_users(now=1_129) == []
    assert await redis_store.due_users(now=1_130) == [42]


@pytest.mark.asyncio
async def test_enqueue_accepts_an_idempotency_key_once(
    redis_store: NotificationRedisStore,
):
    event = notification("tx-1", "First payment")

    assert await redis_store.enqueue(42, event) is True
    assert await redis_store.enqueue(42, event) is False
    assert await redis_store.pending_count(42) == 1


@pytest.mark.asyncio
async def test_enqueue_rejects_a_notification_for_another_user(
    redis_store: NotificationRedisStore,
):
    with pytest.raises(ValueError, match="user_id"):
        await redis_store.enqueue(7, notification("tx-1", "First payment"))


@pytest.mark.asyncio
async def test_state_persists_across_a_new_client_on_the_same_fake_server():
    server = fakeredis.FakeServer()
    first_redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    second_redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    first_store = NotificationRedisStore(
        first_redis, hold_seconds=120, lock_ttl_seconds=30
    )
    second_store = NotificationRedisStore(
        second_redis, hold_seconds=120, lock_ttl_seconds=30
    )
    event = notification("tx-1", "First payment")
    try:
        await first_store.touch(42, now=1_000)
        assert await first_store.enqueue(42, event) is True

        assert await second_store.hold_until(42) == 1_120
        assert await second_store.due_users(now=1_120) == [42]
        assert await second_store.peek(42) == event
        assert await second_store.pending_count(42) == 1
        assert await second_store.enqueue(42, event) is False
    finally:
        await first_redis.aclose()
        await second_redis.aclose()


@pytest.mark.asyncio
async def test_two_stores_enqueue_the_same_event_only_once():
    server = fakeredis.FakeServer()
    first_redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    second_redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    first_store = NotificationRedisStore(
        first_redis, hold_seconds=120, lock_ttl_seconds=30
    )
    second_store = NotificationRedisStore(
        second_redis, hold_seconds=120, lock_ttl_seconds=30
    )
    event = notification("tx-1", "First payment")
    try:
        accepted = await asyncio.gather(
            first_store.enqueue(42, event), second_store.enqueue(42, event)
        )

        assert sorted(accepted) == [False, True]
        assert await first_store.pending_count(42) == 1
    finally:
        await first_redis.aclose()
        await second_redis.aclose()


@pytest.mark.asyncio
async def test_claim_accept_atomically_queues_when_a_touch_wins_the_race():
    """An accept may never bypass a hold that exists at its atomic claim."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    event = notification("tx-claim", "Claimed payment")
    try:
        await store.touch(42, now=1_000)

        assert await store.claim_accept(42, event, now=1_000) == "queued"
        assert await store.claim_accept(42, event, now=1_000) == "duplicate"
        assert await store.peek(42) == event
        assert await store.pending_count(42) == 1
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_claim_accept_keeps_direct_delivery_claim_recoverable_in_fifo_queue():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    event = notification("tx-direct", "Direct payment")
    try:
        assert await store.claim_accept(42, event, now=1_000) == "direct"
        assert await store.claim_accept(42, event, now=1_000) == "duplicate"
        assert await store.peek(42) == event
        assert await store.due_users(now=1_000) == [42]
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_fenced_empty_queue_cleanup_preserves_a_renewed_hold_schedule(
    redis_store: NotificationRedisStore,
):
    event = notification("tx-direct", "Direct payment")
    assert await redis_store.claim_accept(42, event, now=1_000) == "direct"
    assert await redis_store.acquire_lock(42, "owner-token") is True
    assert await redis_store.acknowledge_if_lock_owned(42, event, "owner-token")
    assert await redis_store.touch(42, now=1_000) == 1_120

    assert (
        await redis_store.clear_immediate_due_if_empty_and_lock_owned(
            42, "owner-token", now=1_000
        )
        is False
    )
    assert await redis_store.due_users(now=1_120) == [42]


@pytest.mark.asyncio
async def test_enqueue_keeps_notifications_in_fifo_order(
    redis_store: NotificationRedisStore,
):
    first = notification("tx-1", "First payment")
    second = notification("tx-2", "Second payment")
    await redis_store.enqueue(42, first)
    await redis_store.enqueue(42, second)

    assert await redis_store.peek(42) == first
    assert await redis_store.acknowledge(42, first) is True
    assert await redis_store.peek(42) == second


@pytest.mark.asyncio
async def test_touch_reschedules_user_at_latest_hold_deadline(
    redis_store: NotificationRedisStore,
):
    await redis_store.touch(42, now=1_000)
    await redis_store.touch(42, now=1_050)

    assert await redis_store.due_users(now=1_120) == []
    assert await redis_store.due_users(now=1_170) == [42]


@pytest.mark.asyncio
async def test_acknowledge_rejects_an_unexpected_current_head(
    redis_store: NotificationRedisStore,
):
    first = notification("tx-1", "First payment")
    second = notification("tx-2", "Second payment")
    await redis_store.enqueue(42, first)
    await redis_store.enqueue(42, second)

    assert await redis_store.acknowledge(42, second) is False
    assert await redis_store.peek(42) == first


@pytest.mark.asyncio
async def test_acknowledge_if_lock_owned_keeps_head_when_lease_changed_before_ack(
    redis_store: NotificationRedisStore,
):
    event = notification("tx-1", "First payment")
    await redis_store.enqueue(42, event)
    assert await redis_store.acquire_lock(42, "stale-owner") is True

    assert await redis_store.release_lock(42, "stale-owner") is True
    assert await redis_store.acquire_lock(42, "current-owner") is True

    assert (
        await redis_store.acknowledge_if_lock_owned(42, event, "stale-owner") is False
    )
    assert await redis_store.peek(42) == event


@pytest.mark.asyncio
async def test_due_users_skips_expired_holds_and_fills_a_limited_page():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    try:
        await redis.zadd("notification:due", {"1": 1_000, "2": 1_000})
        await redis.set("notification:hold:3", 1_000)
        await redis.set("notification:hold:4", 1_000)
        await redis.zadd("notification:due", {"3": 1_000, "4": 1_000})

        assert await store.due_users(now=1_000, limit=2) == [3, 4]
        assert await redis.zscore("notification:due", "1") is None
        assert await redis.zscore("notification:due", "2") is None
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_due_users_lua_uses_bounded_queries_and_reaches_users_after_a_stale_prefix():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    original_eval = redis.eval
    scripts: list[str] = []

    async def recording_eval(script, *args, **kwargs):
        scripts.append(script)
        return await original_eval(script, *args, **kwargs)

    redis.eval = recording_eval
    try:
        await redis.zadd(
            "notification:due", {str(user_id): 1_000 for user_id in range(1, 8)}
        )
        await redis.zadd("notification:due", {"90": 1_000, "91": 1_000})
        await redis.set("notification:hold:90", 1_000)
        await redis.set("notification:hold:91", 1_000)

        assert await store.due_users(now=1_000, limit=2) == [90, 91]
        assert "'ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT'" in scripts[0]
        assert await redis.zscore("notification:due", "1") is None
        assert await redis.zscore("notification:due", "7") is None
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_due_users_bounds_each_watch_query_and_reaches_users_after_a_stale_prefix():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    original_pipeline = redis.pipeline
    zrangebyscore_calls: list[dict[str, int]] = []

    def recording_pipeline(*args, **kwargs):
        @asynccontextmanager
        async def context():
            async with original_pipeline(*args, **kwargs) as pipeline:
                original_zrangebyscore = pipeline.zrangebyscore

                async def zrangebyscore(*args, **kwargs):
                    zrangebyscore_calls.append(kwargs)
                    return await original_zrangebyscore(*args, **kwargs)

                pipeline.zrangebyscore = zrangebyscore
                yield pipeline

        return context()

    redis.pipeline = recording_pipeline
    redis.eval = AsyncMock(side_effect=ResponseError("unknown command 'eval'"))
    try:
        await redis.zadd(
            "notification:due", {str(user_id): 1_000 for user_id in range(1, 8)}
        )
        await redis.zadd("notification:due", {"90": 1_000, "91": 1_000})
        await redis.set("notification:hold:90", 1_000)
        await redis.set("notification:hold:91", 1_000)

        assert await store.due_users(now=1_000, limit=2) == [90, 91]
        assert len(zrangebyscore_calls) > 1
        for call in zrangebyscore_calls:
            assert call["num"] <= 2
            assert "start" in call
        assert await redis.zscore("notification:due", "1") is None
        assert await redis.zscore("notification:due", "7") is None
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_due_users_preserves_a_hold_renewed_before_stale_cleanup():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    try:
        await redis.zadd("notification:due", {"42": 1_000})
        # This is the state left when a concurrent touch renewed the hold after
        # a worker had observed the earlier due score.
        await redis.set("notification:hold:42", 1_120)

        assert await store.due_users(now=1_000) == []
        assert await store.hold_until(42) == 1_120
        assert await redis.zscore("notification:due", "42") == 1_120
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_lock_release_requires_owning_token(redis_store: NotificationRedisStore):
    assert await redis_store.acquire_lock(42, "owner-token") is True
    assert await redis_store.acquire_lock(42, "other-token") is False

    assert await redis_store.release_lock(42, "other-token") is False
    assert await redis_store.acquire_lock(42, "other-token") is False
    assert await redis_store.release_lock(42, "owner-token") is True
    assert await redis_store.acquire_lock(42, "other-token") is True


@pytest.mark.asyncio
async def test_lock_renewal_requires_owning_token_and_extends_its_ttl():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=1)
    try:
        assert await store.acquire_lock(42, "owner-token") is True
        await asyncio.sleep(0.75)

        assert await store.renew_lock(42, "other-token") is False
        assert await store.renew_lock(42, "owner-token") is True
        await asyncio.sleep(0.5)
        assert await store.acquire_lock(42, "other-token") is False
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_two_stores_exclude_competing_lock_owners():
    server = fakeredis.FakeServer()
    first_redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    second_redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    first_store = NotificationRedisStore(
        first_redis, hold_seconds=120, lock_ttl_seconds=30
    )
    second_store = NotificationRedisStore(
        second_redis, hold_seconds=120, lock_ttl_seconds=30
    )
    try:
        acquired = await asyncio.gather(
            first_store.acquire_lock(42, "first-owner"),
            second_store.acquire_lock(42, "second-owner"),
        )

        assert sorted(acquired) == [False, True]
    finally:
        await first_redis.aclose()
        await second_redis.aclose()


@pytest.mark.asyncio
async def test_expired_lock_can_be_reacquired_without_stale_owner_releasing_it():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=1)
    try:
        assert await store.acquire_lock(42, "stale-owner") is True
        await asyncio.sleep(1.1)
        assert await store.acquire_lock(42, "new-owner") is True

        assert await store.release_lock(42, "stale-owner") is False
        assert await store.acquire_lock(42, "third-owner") is False
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_holds_expire_after_the_configured_ttl():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=1, lock_ttl_seconds=30)
    try:
        await store.touch(42, now=1_000)
        assert 0 < await redis.ttl("notification:hold:42") <= 1

        await asyncio.sleep(1.1)
        assert await store.hold_until(42) is None
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_enqueue_sets_and_refreshes_configured_dedupe_ttl_without_expiring_queue():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(
        redis,
        hold_seconds=120,
        lock_ttl_seconds=30,
        dedupe_ttl_seconds=2,
    )
    first = notification("tx-1", "First payment")
    second = notification("tx-2", "Second payment")
    try:
        assert await store.enqueue(42, first) is True
        assert 0 < await redis.ttl("notification:dedupe:42") <= 2
        assert await redis.ttl("notification:pending:42") == -1

        await asyncio.sleep(1.1)
        assert await store.enqueue(42, first) is False
        assert await store.enqueue(42, second) is True
        assert 0 < await redis.ttl("notification:dedupe:42") <= 2
        assert await redis.ttl("notification:pending:42") == -1
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_enqueue_rejects_an_unacknowledged_id_after_historical_dedupe_expires():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(
        redis,
        hold_seconds=120,
        lock_ttl_seconds=30,
        dedupe_ttl_seconds=1,
    )
    event = notification("tx-1", "First payment")
    try:
        assert await store.enqueue(42, event) is True
        await asyncio.sleep(1.1)

        assert await redis.exists("notification:dedupe:42") == 0
        assert await store.enqueue(42, event) is False
        assert await store.pending_count(42) == 1
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_enqueue_accepts_after_acknowledgement_and_historical_retention_expiry():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(
        redis,
        hold_seconds=120,
        lock_ttl_seconds=30,
        dedupe_ttl_seconds=1,
    )
    event = notification("tx-1", "First payment")
    try:
        assert await store.enqueue(42, event) is True
        assert await store.acknowledge(42, event) is True
        assert await store.enqueue(42, event) is False

        await asyncio.sleep(1.1)

        assert await store.enqueue(42, event) is True
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_store_supports_default_binary_redis_responses():
    redis = fakeredis.aioredis.FakeRedis()
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    event = notification("tx-1", "First payment")
    try:
        assert await store.enqueue(42, event) is True
        assert await store.peek(42) == event
        assert await store.acknowledge(42, event) is True
        assert await store.acquire_lock(42, "owner-token") is True
        assert await store.release_lock(42, "owner-token") is True
    finally:
        await redis.aclose()
