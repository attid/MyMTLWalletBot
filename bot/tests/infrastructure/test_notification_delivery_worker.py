"""Tests for durable delayed-notification delivery polling."""

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, create_autospec

import fakeredis.aioredis
import pytest

from core.models.blockchain_notification import BlockchainNotification
from infrastructure.services.notification_coordinator import (
    NotificationBadgeRefresher,
    NotificationCoordinator,
)
from infrastructure.services.notification_redis_store import NotificationRedisStore
from infrastructure.services.telegram_delivery_service import NotificationSender
from infrastructure.workers.notification_delivery_worker import (
    NotificationDeliveryWorker,
    NotificationDueStore,
)
from other.config_reader import Settings, config
from start import on_shutdown_dispatcher, on_startup


def notification(notification_id: str, user_id: int = 42) -> BlockchainNotification:
    return BlockchainNotification(
        notification_id=notification_id,
        user_id=user_id,
        text=f"notification {notification_id}",
        created_at=1_000,
        transaction_hash=notification_id,
        event_type="payment",
        event_index=0,
    )


def coordinator(
    store: NotificationRedisStore,
    sender: MagicMock,
    *,
    clock: Callable[[], int],
) -> NotificationCoordinator:
    badge_refresher = create_autospec(
        NotificationBadgeRefresher, instance=True, spec_set=True
    )
    return NotificationCoordinator(
        store=store,
        sender=sender,
        badge_refresher=badge_refresher,
        clock=clock,
    )


@pytest.fixture
async def redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def sender() -> MagicMock:
    return create_autospec(NotificationSender, instance=True, spec_set=True)


@pytest.mark.asyncio
async def test_poll_once_delivers_expired_queued_notification(redis, sender):
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    subject = coordinator(store, sender, clock=lambda: 1_120)
    await store.touch(42, now=1_000)
    await store.enqueue(42, notification("expired"))

    await NotificationDeliveryWorker(
        store=store,
        coordinator=subject,
        poll_interval_seconds=1,
        batch_size=10,
        clock=lambda: 1_120,
    ).poll_once()

    sender.send_notification.assert_awaited_once_with(notification("expired"))


@pytest.mark.asyncio
async def test_poll_once_leaves_renewed_hold_for_coordinator_to_defer(redis, sender):
    store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    await store.touch(42, now=1_000)
    await store.enqueue(42, notification("renewed"))
    subject = coordinator(store, sender, clock=lambda: 1_120)

    original_flush = subject.flush

    async def renew_then_flush(user_id: int, *, reason: str) -> None:
        await store.touch(user_id, now=1_120)
        await original_flush(user_id, reason=reason)

    subject.flush = renew_then_flush  # type: ignore[method-assign]

    await NotificationDeliveryWorker(
        store=store,
        coordinator=subject,
        poll_interval_seconds=1,
        batch_size=10,
        clock=lambda: 1_120,
    ).poll_once()

    sender.send_notification.assert_not_awaited()
    assert await store.hold_until(42) == 1_240


@pytest.mark.asyncio
async def test_two_workers_exclude_each_other_with_shared_redis(redis, sender):
    first_store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    second_store = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    assert (
        await first_store.claim_accept(42, notification("once"), now=1_000) == "direct"
    )
    first = NotificationDeliveryWorker(
        store=first_store,
        coordinator=coordinator(first_store, sender, clock=lambda: 1_000),
        poll_interval_seconds=1,
        batch_size=10,
        clock=lambda: 1_000,
    )
    second = NotificationDeliveryWorker(
        store=second_store,
        coordinator=coordinator(second_store, sender, clock=lambda: 1_000),
        poll_interval_seconds=1,
        batch_size=10,
        clock=lambda: 1_000,
    )

    await asyncio.gather(first.poll_once(), second.poll_once())

    sender.send_notification.assert_awaited_once_with(notification("once"))


@pytest.mark.asyncio
async def test_new_worker_recovers_due_work_from_same_redis_after_restart(
    redis, sender
):
    before_restart = NotificationRedisStore(
        redis, hold_seconds=120, lock_ttl_seconds=30
    )
    await before_restart.touch(42, now=1_000)
    await before_restart.enqueue(42, notification("recovered"))

    after_restart = NotificationRedisStore(redis, hold_seconds=120, lock_ttl_seconds=30)
    await NotificationDeliveryWorker(
        store=after_restart,
        coordinator=coordinator(after_restart, sender, clock=lambda: 1_120),
        poll_interval_seconds=1,
        batch_size=10,
        clock=lambda: 1_120,
    ).poll_once()

    sender.send_notification.assert_awaited_once_with(notification("recovered"))


@pytest.mark.asyncio
async def test_poll_once_logs_one_user_failure_and_continues_with_remaining_users():
    store = create_autospec(NotificationDueStore, instance=True, spec_set=True)
    store.due_users = AsyncMock(return_value=[1, 2])
    coordinator_mock = MagicMock()
    coordinator_mock.flush = AsyncMock(side_effect=[RuntimeError("boom"), None])
    subject = NotificationDeliveryWorker(
        store=store,
        coordinator=coordinator_mock,
        poll_interval_seconds=1,
        batch_size=10,
        clock=lambda: 1_000,
    )

    await subject.poll_once()

    coordinator_mock.flush.assert_has_awaits(
        [call(1, reason="hold_expired"), call(2, reason="hold_expired")]
    )


@pytest.mark.asyncio
async def test_run_can_be_cancelled_while_waiting_for_next_poll():
    store = create_autospec(NotificationDueStore, instance=True, spec_set=True)
    store.due_users = AsyncMock(return_value=[])
    subject = NotificationDeliveryWorker(
        store=store,
        coordinator=MagicMock(),
        poll_interval_seconds=60,
        batch_size=10,
        clock=lambda: 1_000,
    )
    task = asyncio.create_task(subject.run())
    await asyncio.sleep(0)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


def test_worker_options_and_hold_default_are_configurable():
    assert Settings.model_fields["notification_hold_seconds"].default == 120
    assert (
        Settings.model_fields["notification_delivery_poll_interval_seconds"].default > 0
    )
    assert Settings.model_fields["notification_delivery_batch_size"].default > 0
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        NotificationDeliveryWorker(
            store=MagicMock(),
            coordinator=MagicMock(),
            poll_interval_seconds=0,
            batch_size=1,
        )
    for interval in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="poll_interval_seconds"):
            NotificationDeliveryWorker(
                store=MagicMock(),
                coordinator=MagicMock(),
                poll_interval_seconds=interval,
                batch_size=1,
            )
    with pytest.raises(ValueError, match="batch_size"):
        NotificationDeliveryWorker(
            store=MagicMock(),
            coordinator=MagicMock(),
            poll_interval_seconds=1,
            batch_size=0,
        )


@pytest.mark.parametrize("interval", [0, -1, float("nan"), float("inf"), float("-inf")])
def test_settings_reject_non_positive_or_non_finite_notification_poll_interval(
    interval: float,
) -> None:
    values = config.model_dump(mode="python")
    values["notification_delivery_poll_interval_seconds"] = interval

    with pytest.raises(ValueError, match="notification_delivery_poll_interval_seconds"):
        Settings.model_validate(values)


@pytest.mark.asyncio
async def test_shutdown_stops_notification_producers_and_awaits_worker_before_redis_then_broker(
    monkeypatch,
):
    import start

    started = asyncio.Event()
    stopped = asyncio.Event()

    async def run() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    worker = SimpleNamespace(run=run)
    order: list[str] = []

    async def stop_notification_service() -> None:
        order.append("notification_service.stop")

    async def close_notification_redis() -> None:
        assert stopped.is_set()
        order.append("notification_redis.aclose")

    async def stop_broker() -> None:
        assert stopped.is_set()
        assert order[-1] == "notification_redis.aclose"
        order.append("broker.stop")

    notification_redis = AsyncMock()
    notification_redis.aclose.side_effect = close_notification_redis
    notification_service = AsyncMock()
    notification_service.stop.side_effect = stop_notification_service
    app_context = SimpleNamespace(
        notification_service=notification_service,
        notification_delivery_worker=worker,
        notification_redis=notification_redis,
    )
    dispatcher: dict[str, object] = {"app_context": app_context}
    bot = AsyncMock()
    monkeypatch.setattr(start, "start_broker", AsyncMock())
    monkeypatch.setattr(start, "stop_broker", stop_broker)
    monkeypatch.setattr(start, "set_commands", AsyncMock())
    monkeypatch.setattr(start.config, "test_mode", True)
    monkeypatch.setattr(start.config, "admins", [42])

    await on_startup(bot, dispatcher)  # type: ignore[arg-type]
    await started.wait()
    await on_shutdown_dispatcher(dispatcher, bot)  # type: ignore[arg-type]

    assert stopped.is_set()
    notification_service.stop.assert_awaited_once()
    notification_redis.aclose.assert_awaited_once()
    assert order == [
        "notification_service.stop",
        "notification_redis.aclose",
        "broker.stop",
    ]
