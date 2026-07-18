"""Tests for delayed blockchain notification coordination."""

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, call, create_autospec

import pytest
import fakeredis.aioredis
from loguru import logger
from core.models.blockchain_notification import BlockchainNotification
from infrastructure.services.notification_coordinator import (
    NotificationBadgeRefresher,
    NotificationCoordinator,
    NotificationSender,
    NotificationStore,
)
from infrastructure.services.notification_redis_store import NotificationRedisStore


def notification(notification_id: str, text: str) -> BlockchainNotification:
    return BlockchainNotification(
        notification_id=notification_id,
        user_id=42,
        event_type="payment",
        text=text,
        created_at=1_000,
        transaction_hash=notification_id,
        event_index=0,
    )


@pytest.fixture
def store() -> MagicMock:
    mock = create_autospec(NotificationStore, instance=True, spec_set=True)
    mock.acquire_lock.return_value = True
    mock.acknowledge_if_lock_owned.return_value = True
    mock.release_lock.return_value = True
    return mock


@pytest.fixture
def sender() -> MagicMock:
    return create_autospec(NotificationSender, instance=True, spec_set=True)


@pytest.fixture
def badge_refresher() -> MagicMock:
    return create_autospec(NotificationBadgeRefresher, instance=True, spec_set=True)


def coordinator(
    store: MagicMock,
    sender: MagicMock,
    badge_refresher: MagicMock,
    *,
    now: int = 1_000,
    heartbeat_interval: float = 0.01,
    delivery_timeout_seconds: float | None = None,
) -> NotificationCoordinator:
    kwargs = {}
    if delivery_timeout_seconds is not None:
        kwargs["delivery_timeout_seconds"] = delivery_timeout_seconds
    return NotificationCoordinator(
        store=store,
        sender=sender,
        badge_refresher=badge_refresher,
        clock=MagicMock(spec=Callable, return_value=now),
        token_factory=MagicMock(return_value="flush-token"),
        heartbeat_interval=heartbeat_interval,
        **kwargs,
    )


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_coordinator_rejects_a_non_positive_or_non_finite_delivery_timeout(
    store: MagicMock,
    sender: MagicMock,
    badge_refresher: MagicMock,
    timeout: float,
) -> None:
    with pytest.raises(
        ValueError, match="delivery_timeout_seconds must be finite and positive"
    ):
        NotificationCoordinator(
            store=store,
            sender=sender,
            badge_refresher=badge_refresher,
            delivery_timeout_seconds=timeout,
        )


@pytest.mark.asyncio
async def test_touch_delegates_to_the_store_with_the_coordinator_clock(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    store.touch.return_value = 1_120

    hold_until = await coordinator(store, sender, badge_refresher).touch(42)

    assert hold_until == 1_120
    store.touch.assert_awaited_once_with(42, now=1_000)


@pytest.mark.asyncio
async def test_accept_delivers_immediately_without_an_active_hold(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    store.claim_accept.return_value = "direct"
    subject = coordinator(store, sender, badge_refresher)
    subject.flush = AsyncMock()  # type: ignore[method-assign]

    await subject.accept(event)

    store.claim_accept.assert_awaited_once_with(42, event, now=1_000)
    subject.flush.assert_awaited_once_with(42, reason="accepted")
    sender.send_notification.assert_not_awaited()
    badge_refresher.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_accept_queues_and_refreshes_badge_when_hold_is_active(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    store.claim_accept.return_value = "queued"

    await coordinator(store, sender, badge_refresher).accept(event)

    badge_refresher.refresh.assert_awaited_once_with(42)
    sender.send_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_accept_rechecks_when_an_expired_hold_was_concurrently_renewed(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    store.claim_accept.return_value = "queued"

    await coordinator(store, sender, badge_refresher).accept(event)

    store.claim_accept.assert_awaited_once_with(42, event, now=1_000)
    badge_refresher.refresh.assert_awaited_once_with(42)
    sender.send_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_flush_keeps_queue_held_when_hold_remains_active(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    store.hold_until.return_value = 1_120

    await coordinator(store, sender, badge_refresher).flush(42, reason="worker")

    store.peek.assert_not_awaited()
    sender.send_notification.assert_not_awaited()
    store.release_lock.assert_awaited_once_with(42, "flush-token")


@pytest.mark.asyncio
async def test_flush_preserves_a_renewed_hold_observed_during_expiry_release(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    store.hold_until.return_value = 1_000
    store.peek.return_value = None

    await coordinator(store, sender, badge_refresher).flush(42, reason="expiry")

    store.release_hold_if_unchanged.assert_awaited_once_with(42, 1_000, now=1_000)
    store.peek.assert_awaited_once_with(42)
    sender.send_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_flush_cleans_an_expired_due_schedule_only_after_queue_is_empty(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    store.hold_until.return_value = 1_000
    store.peek.side_effect = [event, None]
    store.renew_lock.return_value = True

    await coordinator(store, sender, badge_refresher).flush(42, reason="expiry")

    assert store.mock_calls == [
        call.acquire_lock(42, "flush-token"),
        call.hold_until(42),
        call.peek(42),
        call.renew_lock(42, "flush-token"),
        call.hold_until(42),
        call.acknowledge_if_lock_owned(42, event, "flush-token"),
        call.peek(42),
        call.release_hold_if_unchanged(42, 1_000, now=1_000),
        call.clear_immediate_due_if_empty_and_lock_owned(42, "flush-token", now=1_000),
        call.release_lock(42, "flush-token"),
    ]


@pytest.mark.asyncio
async def test_flush_ignores_an_active_hold_when_requested(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    store.hold_until.return_value = 1_120
    store.peek.side_effect = [event, None]

    await coordinator(store, sender, badge_refresher).flush(
        42, ignore_hold=True, reason="badge"
    )

    sender.send_notification.assert_awaited_once_with(event)
    store.acknowledge_if_lock_owned.assert_awaited_once_with(42, event, "flush-token")
    badge_refresher.refresh.assert_awaited_once_with(42)


@pytest.mark.asyncio
async def test_flush_rechecks_hold_before_each_send_and_defers_after_a_new_touch(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    store.hold_until.side_effect = [None, 1_120]
    store.peek.return_value = event
    store.renew_lock.return_value = True

    await coordinator(store, sender, badge_refresher).flush(42, reason="worker")

    sender.send_notification.assert_not_awaited()
    store.acknowledge_if_lock_owned.assert_not_awaited()


@pytest.mark.asyncio
async def test_flush_rechecks_lease_after_hold_check_before_sending(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    lease_lost = asyncio.Event()

    async def hold_until(_: int) -> int | None:
        if store.hold_until.await_count == 2:
            lease_lost.set()
        return None

    store.hold_until.side_effect = hold_until
    store.peek.side_effect = [event, None]
    store.renew_lock.return_value = True

    await coordinator(store, sender, badge_refresher)._flush_owned(
        42,
        "flush-token",
        reason="worker",
        lease_lost=lease_lost,
    )

    sender.send_notification.assert_not_awaited()
    store.acknowledge_if_lock_owned.assert_not_awaited()


@pytest.mark.asyncio
async def test_flush_cancels_a_stuck_sender_and_releases_its_lock(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("stuck", "Stuck payment")
    store.hold_until.return_value = None
    store.peek.return_value = event
    store.renew_lock.return_value = True
    sender_cancelled = asyncio.Event()

    async def stuck_send(_: BlockchainNotification) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            sender_cancelled.set()
            raise

    sender.send_notification.side_effect = stuck_send
    records = []
    sink_id = logger.add(lambda message: records.append(message.record), level="DEBUG")
    try:
        await asyncio.wait_for(
            coordinator(
                store,
                sender,
                badge_refresher,
                delivery_timeout_seconds=0.01,
            ).flush(42, reason="flow_completed"),
            timeout=0.2,
        )
    finally:
        logger.remove(sink_id)

    assert sender_cancelled.is_set()
    store.acknowledge_if_lock_owned.assert_not_awaited()
    badge_refresher.refresh.assert_not_awaited()
    store.release_lock.assert_awaited_once_with(42, "flush-token")
    timeout_record = next(
        record
        for record in records
        if record["extra"].get("event") == "notification_delivery_timed_out"
    )
    assert "user_id=42" in timeout_record["message"]
    assert "notification_id=stuck" in timeout_record["message"]
    assert "reason=flow_completed" in timeout_record["message"]
    assert "timeout_seconds=0.01" in timeout_record["message"]
    release_record = next(
        record
        for record in records
        if record["extra"].get("event") == "notification_flush_lock_released"
    )
    assert "user_id=42" in release_record["message"]
    assert "reason=flow_completed" in release_record["message"]
    assert "released=True" in release_record["message"]


@pytest.mark.asyncio
async def test_flush_renews_its_owned_lock_before_slow_notification_delivery(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    store.hold_until.return_value = None
    store.peek.side_effect = [event, None]
    store.renew_lock.return_value = True

    await coordinator(store, sender, badge_refresher).flush(42, reason="worker")

    store.renew_lock.assert_awaited_once_with(42, "flush-token")
    sender.send_notification.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_flush_stops_when_ownership_changes_immediately_before_ack(
    sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)

    async def send_then_replace_owner(_: BlockchainNotification) -> None:
        assert await store.release_lock(42, "flush-token") is True
        assert await store.acquire_lock(42, "new-owner") is True

    sender.send_notification.side_effect = send_then_replace_owner
    try:
        assert await store.claim_accept(42, event, now=1_000) == "direct"

        await coordinator(store, sender, badge_refresher).flush(42, reason="worker")

        sender.send_notification.assert_awaited_once_with(event)
        assert await store.peek(42) == event
        assert await store.pending_count(42) == 1
        badge_refresher.refresh.assert_not_awaited()
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_badge_refresh_failure_does_not_fail_accept(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    store.claim_accept.return_value = "queued"
    badge_refresher.refresh.side_effect = RuntimeError("old message")

    await coordinator(store, sender, badge_refresher).accept(event)

    sender.send_notification.assert_not_awaited()


@pytest.mark.asyncio
async def test_badge_refresh_failure_does_not_stop_fifo_flush(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    first = notification("first", "First payment")
    second = notification("second", "Second payment")
    store.hold_until.return_value = None
    store.peek.side_effect = [first, second, None]
    store.renew_lock.return_value = True
    badge_refresher.refresh.side_effect = RuntimeError("old message")

    await coordinator(store, sender, badge_refresher).flush(42, reason="worker")

    sender.send_notification.assert_has_awaits([call(first), call(second)])
    store.acknowledge_if_lock_owned.assert_has_awaits(
        [call(42, first, "flush-token"), call(42, second, "flush-token")]
    )


@pytest.mark.asyncio
async def test_complete_flow_releases_hold_and_flushes_immediately(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    subject = coordinator(store, sender, badge_refresher)
    store.hold_until.return_value = 1_120
    store.release_hold_if_unchanged.return_value = True
    subject._flush_owned = AsyncMock()  # type: ignore[method-assign]

    await subject.complete_flow(42)

    store.acquire_lock.assert_awaited_once_with(42, "flush-token")
    store.release_hold_if_unchanged.assert_awaited_once_with(42, 1_120, now=1_000)
    flush_call = subject._flush_owned.await_args
    assert flush_call is not None
    assert flush_call.args == (42, "flush-token")
    assert flush_call.kwargs["reason"] == "flow_completed"
    assert isinstance(flush_call.kwargs["lease_lost"], asyncio.Event)


@pytest.mark.asyncio
async def test_complete_flow_retries_a_busy_lock_and_releases_its_observed_generation(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    """A terminal callback must hand off to an in-flight flush instead of dropping it."""
    subject = coordinator(store, sender, badge_refresher)
    store.hold_until.return_value = 1_120
    store.acquire_lock.side_effect = [False, True]
    store.release_hold_if_unchanged.return_value = True
    subject._flush_owned = AsyncMock()  # type: ignore[method-assign]

    await subject.complete_flow(42)

    store.hold_until.assert_awaited_once_with(42)
    store.acquire_lock.assert_has_awaits(
        [call(42, "flush-token"), call(42, "flush-token")]
    )
    store.release_hold_if_unchanged.assert_awaited_once_with(42, 1_120, now=1_000)
    subject._flush_owned.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_flow_does_not_flush_when_a_new_touch_replaces_its_generation(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    subject = coordinator(store, sender, badge_refresher)
    store.hold_until.return_value = 1_120
    store.release_hold_if_unchanged.return_value = False
    subject._flush_owned = AsyncMock()  # type: ignore[method-assign]

    await subject.complete_flow(42)

    subject._flush_owned.assert_not_awaited()
    store.release_lock.assert_awaited_once_with(42, "flush-token")


@pytest.mark.asyncio
async def test_complete_flow_does_not_send_when_touch_arrives_after_its_release(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    event = notification("first", "First payment")
    store.hold_until.side_effect = [1_120, 1_240]
    store.release_hold_if_unchanged.return_value = True
    store.peek.return_value = event

    await coordinator(store, sender, badge_refresher).complete_flow(42)

    sender.send_notification.assert_not_awaited()
    store.acknowledge_if_lock_owned.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_direct_accept_keeps_its_claimed_event_for_retry() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    sender = create_autospec(NotificationSender, instance=True, spec_set=True)
    sender.send_notification.side_effect = RuntimeError("telegram unavailable")
    badge_refresher = create_autospec(
        NotificationBadgeRefresher, instance=True, spec_set=True
    )
    event = notification("first", "First payment")
    subject = NotificationCoordinator(
        store=store,
        sender=sender,
        badge_refresher=badge_refresher,
        clock=lambda: 1_000,
        token_factory=lambda: "owner-token",
    )
    try:
        await subject.accept(event)

        assert await store.peek(42) == event
        assert await store.pending_count(42) == 1
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_direct_accept_between_final_empty_peek_and_expired_hold_release_is_recoverable() -> (
    None
):
    class PausingStore(NotificationRedisStore):
        def __init__(self, redis: fakeredis.aioredis.FakeRedis) -> None:
            super().__init__(redis, hold_seconds=120, lock_ttl_seconds=30)
            self.final_empty_peeked = asyncio.Event()
            self.continue_flush = asyncio.Event()
            self._pause_next_empty_peek = False

        async def peek(self, user_id: int) -> BlockchainNotification | None:
            item = await super().peek(user_id)
            if item is None and self._pause_next_empty_peek:
                self._pause_next_empty_peek = False
                self.final_empty_peeked.set()
                await self.continue_flush.wait()
            return item

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = PausingStore(redis)
    deliveries: list[BlockchainNotification] = []
    sender = create_autospec(NotificationSender, instance=True, spec_set=True)
    sender.send_notification.side_effect = deliveries.append
    badge_refresher = create_autospec(
        NotificationBadgeRefresher, instance=True, spec_set=True
    )
    first = notification("first", "First payment")
    second = notification("second", "Second payment")
    subject = NotificationCoordinator(
        store=store,
        sender=sender,
        badge_refresher=badge_refresher,
        clock=lambda: 1_120,
        token_factory=lambda: "owner-token",
    )
    try:
        assert await store.touch(42, now=1_000) == 1_120
        assert await store.claim_accept(42, first, now=1_000) == "queued"
        store._pause_next_empty_peek = True
        first_flush = asyncio.create_task(subject.flush(42, reason="worker"))
        await store.final_empty_peeked.wait()

        await subject.accept(second)
        store.continue_flush.set()
        await first_flush

        assert await store.due_users(now=1_120) == [42]
        await subject.flush(42, reason="worker")
        assert deliveries == [first, second]
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_heartbeat_keeps_lock_owned_during_a_send_past_multiple_ttls() -> None:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=1)
    event = notification("first", "First payment")
    await store.claim_accept(42, event, now=1_000)
    started = asyncio.Event()
    release_send = asyncio.Event()
    deliveries: list[BlockchainNotification] = []

    async def slow_send(item: BlockchainNotification) -> None:
        deliveries.append(item)
        started.set()
        await release_send.wait()

    sender = create_autospec(NotificationSender, instance=True, spec_set=True)
    sender.send_notification.side_effect = slow_send
    badge_refresher = create_autospec(
        NotificationBadgeRefresher, instance=True, spec_set=True
    )
    first = NotificationCoordinator(
        store=store,
        sender=sender,
        badge_refresher=badge_refresher,
        clock=lambda: 1_000,
        token_factory=lambda: "first-owner",
        heartbeat_interval=0.05,
    )
    second = NotificationCoordinator(
        store=store,
        sender=sender,
        badge_refresher=badge_refresher,
        clock=lambda: 1_000,
        token_factory=lambda: "second-owner",
        heartbeat_interval=0.05,
    )
    try:
        first_flush = asyncio.create_task(first.flush(42, reason="worker"))
        await started.wait()
        await asyncio.sleep(2.1)

        await second.flush(42, reason="worker")

        assert deliveries == [event]
        release_send.set()
        await first_flush
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_flush_stops_after_heartbeat_loses_lock_while_a_send_is_blocked(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    first = notification("first", "First payment")
    second = notification("second", "Second payment")
    store.hold_until.return_value = None
    store.peek.side_effect = [first, second, None]
    send_started = asyncio.Event()
    release_send = asyncio.Event()

    async def blocked_send(item: BlockchainNotification) -> None:
        send_started.set()
        await release_send.wait()

    sender.send_notification.side_effect = blocked_send
    store.renew_lock.side_effect = [True, False]
    subject = coordinator(store, sender, badge_refresher, heartbeat_interval=0.01)

    flush_task = asyncio.create_task(subject.flush(42, reason="worker"))
    await send_started.wait()
    await asyncio.sleep(0.02)
    release_send.set()
    await flush_task

    sender.send_notification.assert_awaited_once_with(first)
    store.acquire_lock.assert_has_awaits(
        [call(42, "flush-token"), call(42, "flush-token")]
    )
    store.acknowledge_if_lock_owned.assert_awaited_once_with(42, first, "flush-token")
    badge_refresher.refresh.assert_awaited_once_with(42)
    store.release_lock.assert_has_awaits(
        [call(42, "flush-token"), call(42, "flush-token")]
    )


@pytest.mark.asyncio
async def test_flush_acknowledges_a_successful_send_after_reacquiring_lost_lease(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    """A completed Telegram send gets an acknowledgement-only recovery, not a resend."""
    event = notification("first", "First payment")
    lease_lost = asyncio.Event()
    store.hold_until.return_value = None
    store.peek.return_value = event
    store.renew_lock.return_value = True
    store.acquire_lock.return_value = True

    async def send_then_lose_lease(_: BlockchainNotification) -> None:
        lease_lost.set()

    sender.send_notification.side_effect = send_then_lose_lease
    tokens = iter(("recovery-token",))
    subject = NotificationCoordinator(
        store=store,
        sender=sender,
        badge_refresher=badge_refresher,
        clock=lambda: 1_000,
        token_factory=lambda: next(tokens),
        heartbeat_interval=0.01,
    )

    await subject._flush_owned(
        42, "flush-token", reason="worker", lease_lost=lease_lost
    )

    sender.send_notification.assert_awaited_once_with(event)
    store.acquire_lock.assert_awaited_once_with(42, "recovery-token")
    store.acknowledge_if_lock_owned.assert_awaited_once_with(
        42, event, "recovery-token"
    )


@pytest.mark.asyncio
async def test_two_workers_do_not_resend_after_first_worker_loses_lease_post_send() -> (
    None
):
    """A real Redis queue is acknowledged by recovery before another worker retries it."""

    class LeaseLosingStore(NotificationRedisStore):
        def __init__(self, redis: fakeredis.aioredis.FakeRedis) -> None:
            super().__init__(redis, hold_seconds=120, lock_ttl_seconds=30)
            self.lose_lease = asyncio.Event()
            self.lease_lost = asyncio.Event()
            self._lost_once = False

        async def renew_lock(self, user_id: int, token: str) -> bool:
            if self.lose_lease.is_set() and not self._lost_once:
                self._lost_once = True
                assert await self.release_lock(user_id, token)
                self.lease_lost.set()
                return False
            return await super().renew_lock(user_id, token)

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = LeaseLosingStore(redis)
    event = notification("first", "First payment")
    deliveries: list[BlockchainNotification] = []
    sender = create_autospec(NotificationSender, instance=True, spec_set=True)

    async def send_then_lose_lease(item: BlockchainNotification) -> None:
        deliveries.append(item)
        store.lose_lease.set()
        await store.lease_lost.wait()

    sender.send_notification.side_effect = send_then_lose_lease
    badge_refresher = create_autospec(
        NotificationBadgeRefresher, instance=True, spec_set=True
    )
    first_tokens = iter(("first-token", "recovery-token"))
    first = NotificationCoordinator(
        store=store,
        sender=sender,
        badge_refresher=badge_refresher,
        clock=lambda: 1_000,
        token_factory=lambda: next(first_tokens),
        heartbeat_interval=0.01,
    )
    second = NotificationCoordinator(
        store=store,
        sender=sender,
        badge_refresher=badge_refresher,
        clock=lambda: 1_000,
        token_factory=lambda: "second-token",
        heartbeat_interval=0.01,
    )
    try:
        assert await store.claim_accept(42, event, now=1_000) == "direct"

        await first.flush(42, reason="worker")
        await second.flush(42, reason="worker")

        assert deliveries == [event]
        assert await store.pending_count(42) == 0
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_flush_acknowledges_deliveries_in_fifo_order_and_stops_on_failure(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    first = notification("first", "First payment")
    second = notification("second", "Second payment")
    store.hold_until.return_value = None
    store.peek.side_effect = [first, second]
    sender.send_notification.side_effect = [None, RuntimeError("telegram unavailable")]
    await coordinator(store, sender, badge_refresher).flush(42, reason="worker")

    assert sender.send_notification.await_args_list[0].args == (first,)
    assert sender.send_notification.await_args_list[1].args == (second,)
    store.acknowledge_if_lock_owned.assert_awaited_once_with(42, first, "flush-token")
    badge_refresher.refresh.assert_awaited_once_with(42)
    store.release_lock.assert_awaited_once_with(42, "flush-token")

    sender.send_notification.side_effect = None
    store.peek.side_effect = [second, None]
    await coordinator(store, sender, badge_refresher).flush(42, reason="retry")

    store.acknowledge_if_lock_owned.assert_has_awaits(
        [call(42, first, "flush-token"), call(42, second, "flush-token")]
    )
    store.release_lock.assert_has_awaits(
        [call(42, "flush-token"), call(42, "flush-token")]
    )


@pytest.mark.asyncio
async def test_flush_does_not_enter_when_another_owner_has_the_lock(
    store: MagicMock, sender: MagicMock, badge_refresher: MagicMock
) -> None:
    store.acquire_lock.return_value = False
    records = []
    sink_id = logger.add(lambda message: records.append(message.record), level="INFO")
    try:
        await coordinator(store, sender, badge_refresher).flush(42, reason="worker")
    finally:
        logger.remove(sink_id)

    store.hold_until.assert_not_awaited()
    sender.send_notification.assert_not_awaited()
    store.release_lock.assert_not_awaited()
    contention_record = next(
        record
        for record in records
        if record["extra"].get("event") == "notification_flush_lock_unavailable"
    )
    assert "user_id=42" in contention_record["message"]
    assert "reason=worker" in contention_record["message"]
