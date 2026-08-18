"""Coordinate delayed, ordered blockchain notification delivery."""

import asyncio
from contextlib import suppress
import math
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Protocol

from loguru import logger

from core.models.blockchain_notification import BlockchainNotification

DEFAULT_DELIVERY_TIMEOUT_SECONDS = 30.0
DEFAULT_LOCK_LIFETIME_SECONDS = 90.0
DEFAULT_BADGE_TIMEOUT_SECONDS = 10.0


class NotificationStore(Protocol):
    """The narrow persistence boundary needed by notification delivery."""

    async def touch(self, user_id: int, *, now: int) -> int: ...

    async def touch_with_generation(
        self, user_id: int, *, now: int
    ) -> tuple[int, int]: ...

    async def release_hold_if_unchanged(
        self, user_id: int, expected_hold_until: int, *, now: int
    ) -> bool: ...

    async def release_hold_generation_if_unchanged(
        self, user_id: int, expected_generation: int, *, now: int
    ) -> bool: ...

    async def hold_until(self, user_id: int) -> int | None: ...

    async def hold_snapshot(self, user_id: int) -> tuple[int, int] | None: ...

    async def enqueue(
        self, user_id: int, notification: BlockchainNotification
    ) -> bool: ...

    async def claim_accept(
        self, user_id: int, notification: BlockchainNotification, *, now: int
    ) -> str: ...

    async def peek(self, user_id: int) -> BlockchainNotification | None: ...

    async def acknowledge_if_lock_owned(
        self, user_id: int, expected_head: BlockchainNotification, token: str
    ) -> bool: ...

    async def acquire_lock(self, user_id: int, token: str) -> bool: ...

    async def release_lock(self, user_id: int, token: str) -> bool: ...

    async def renew_lock(self, user_id: int, token: str) -> bool: ...

    async def clear_immediate_due_if_empty_and_lock_owned(
        self, user_id: int, token: str, *, now: int
    ) -> bool: ...


class NotificationBadgeRefresher(Protocol):
    """Best-effort UI badge update owned by the presentation adapter."""

    async def refresh(self, user_id: int) -> None: ...


class NotificationSender(Protocol):
    """Deliver a queued notification through the application's notification path."""

    async def send_notification(self, notification: BlockchainNotification) -> None: ...


class NotificationCoordinator:
    """Own notification hold, queue, and delivery behavior."""

    def __init__(
        self,
        *,
        store: NotificationStore,
        sender: NotificationSender,
        badge_refresher: NotificationBadgeRefresher,
        clock: Callable[[], int] | None = None,
        token_factory: Callable[[], str] | None = None,
        lock_ttl_seconds: float = 30,
        heartbeat_interval: float | None = None,
        delivery_timeout_seconds: float = DEFAULT_DELIVERY_TIMEOUT_SECONDS,
        lock_lifetime_seconds: float = DEFAULT_LOCK_LIFETIME_SECONDS,
        badge_timeout_seconds: float = DEFAULT_BADGE_TIMEOUT_SECONDS,
    ) -> None:
        if lock_ttl_seconds <= 0:
            raise ValueError("lock_ttl_seconds must be positive")
        derived_heartbeat_interval = lock_ttl_seconds / 3
        selected_heartbeat_interval = (
            derived_heartbeat_interval
            if heartbeat_interval is None
            else heartbeat_interval
        )
        if not 0 < selected_heartbeat_interval < lock_ttl_seconds:
            raise ValueError(
                "heartbeat_interval must be greater than zero and below TTL"
            )
        if not math.isfinite(delivery_timeout_seconds) or delivery_timeout_seconds <= 0:
            raise ValueError("delivery_timeout_seconds must be finite and positive")
        if not math.isfinite(lock_lifetime_seconds) or lock_lifetime_seconds <= 0:
            raise ValueError("lock_lifetime_seconds must be finite and positive")
        if not math.isfinite(badge_timeout_seconds) or badge_timeout_seconds <= 0:
            raise ValueError("badge_timeout_seconds must be finite and positive")
        self._store = store
        self._sender = sender
        self._badge_refresher = badge_refresher
        self._clock = clock or _unix_time
        self._token_factory = token_factory or _new_token
        self._heartbeat_interval = selected_heartbeat_interval
        self._delivery_timeout_seconds = delivery_timeout_seconds
        self._lock_lifetime_seconds = lock_lifetime_seconds
        self._badge_timeout_seconds = badge_timeout_seconds
        self._flow_generation_context: ContextVar[tuple[int, int | None] | None] = (
            ContextVar(f"notification_flow_generation_{id(self)}", default=None)
        )

    async def touch(self, user_id: int) -> int:
        """Start or extend the user's sliding activity hold."""
        hold_until, generation = await self._store.touch_with_generation(
            user_id, now=self._clock()
        )
        self._flow_generation_context.set((user_id, generation))
        logger.bind(event="notification_hold_touched", user_id=user_id).info(
            "notification hold touched"
        )
        return hold_until

    async def capture_flow_generation(
        self, user_id: int
    ) -> Token[tuple[int, int | None] | None]:
        """Fence completion to the hold observed when this update began."""
        snapshot = await self._store.hold_snapshot(user_id)
        generation = None if snapshot is None else snapshot[1]
        return self._flow_generation_context.set((user_id, generation))

    def reset_flow_generation(
        self, token: Token[tuple[int, int | None] | None]
    ) -> None:
        """Restore the task-local completion fence after an update finishes."""
        self._flow_generation_context.reset(token)

    async def accept(self, notification: BlockchainNotification) -> None:
        """Atomically claim an event, retaining it before any Telegram send."""
        result = await self._store.claim_accept(
            notification.user_id, notification, now=self._clock()
        )
        if result == "direct":
            await self.flush(notification.user_id, reason="accepted")
            logger.bind(
                event="notification_direct_claimed",
                user_id=notification.user_id,
                notification_id=notification.notification_id,
            ).info("notification claimed for immediate delivery")
            return
        if result == "queued":
            await self._refresh_badge(notification.user_id)
            logger.bind(
                event="notification_queued",
                user_id=notification.user_id,
                notification_id=notification.notification_id,
            ).info("notification queued during active hold")
        elif result == "duplicate":
            logger.bind(
                event="notification_duplicate_ignored",
                user_id=notification.user_id,
                notification_id=notification.notification_id,
            ).info("duplicate notification ignored")
        else:
            raise RuntimeError(f"unknown notification accept result: {result}")

    async def flush(
        self, user_id: int, *, ignore_hold: bool = False, reason: str
    ) -> None:
        """Flush a user's FIFO queue while holding the per-user delivery lock."""
        token = self._token_factory()
        if not await self._store.acquire_lock(user_id, token):
            logger.bind(
                event="notification_flush_lock_unavailable",
                user_id=user_id,
                reason=reason,
            ).info(
                f"notification flush skipped because lock is owned: "
                f"user_id={user_id} reason={reason}"
            )
            return

        await self._flush_with_owned_lock(
            user_id, token, ignore_hold=ignore_hold, reason=reason
        )

    async def _flush_owned(
        self,
        user_id: int,
        token: str,
        *,
        ignore_hold: bool = False,
        reason: str,
        lease_lost: asyncio.Event | None = None,
        progress: dict[str, object] | None = None,
    ) -> bool:
        """Flush with an already-held lock, rechecking the hold per item."""
        badge_refresh_needed = False

        def mark_stage(stage: str, notification_id: str | None = None) -> None:
            if progress is not None:
                progress["stage"] = stage
                progress["notification_id"] = notification_id

        expired_hold_until: int | None = None
        if not ignore_hold:
            mark_stage("hold")
            can_flush, expired_hold_until = await self._hold_allows_flush(user_id)
            if not can_flush:
                logger.bind(
                    event="notification_flush_held", user_id=user_id, reason=reason
                ).info("notification flush deferred by active hold")
                return badge_refresh_needed

        while True:
            mark_stage("peek")
            notification = await self._store.peek(user_id)
            if notification is None:
                break
            mark_stage("renew", notification.notification_id)
            if lease_lost is not None and lease_lost.is_set():
                return badge_refresh_needed
            if not await self._store.renew_lock(user_id, token):
                logger.bind(
                    event="notification_flush_lock_lost", user_id=user_id, reason=reason
                ).warning("notification flush stopped after lock ownership was lost")
                return badge_refresh_needed

            if not ignore_hold:
                mark_stage("hold", notification.notification_id)
                can_flush, observed_expired_hold = await self._hold_allows_flush(
                    user_id
                )
                if not can_flush:
                    logger.bind(
                        event="notification_flush_held", user_id=user_id, reason=reason
                    ).info("notification flush deferred by renewed hold")
                    return badge_refresh_needed
                if observed_expired_hold is not None:
                    expired_hold_until = observed_expired_hold

            if lease_lost is not None and lease_lost.is_set():
                return badge_refresh_needed

            try:
                mark_stage("send", notification.notification_id)
                async with asyncio.timeout(self._delivery_timeout_seconds):
                    await self._sender.send_notification(notification)
            except TimeoutError:
                logger.bind(
                    event="notification_delivery_timed_out",
                    user_id=user_id,
                    notification_id=notification.notification_id,
                    reason=reason,
                    timeout_seconds=self._delivery_timeout_seconds,
                ).warning(
                    f"notification delivery timed out; queue head retained: "
                    f"user_id={user_id} "
                    f"notification_id={notification.notification_id} "
                    f"reason={reason} "
                    f"timeout_seconds={self._delivery_timeout_seconds}"
                )
                return badge_refresh_needed
            except Exception:
                logger.bind(
                    event="notification_delivery_failed",
                    user_id=user_id,
                    notification_id=notification.notification_id,
                    reason=reason,
                ).exception("notification delivery failed; queue head retained")
                return badge_refresh_needed

            mark_stage("ack", notification.notification_id)
            if not await self._store.acknowledge_if_lock_owned(
                user_id, notification, token
            ):
                if await self._acknowledge_after_lease_loss(user_id, notification):
                    return badge_refresh_needed
                logger.bind(
                    event="notification_acknowledgement_lost",
                    user_id=user_id,
                    notification_id=notification.notification_id,
                    reason=reason,
                ).warning("notification acknowledgement did not match queue head")
                return badge_refresh_needed

            badge_refresh_needed = True
            logger.bind(
                event="notification_delivered",
                user_id=user_id,
                notification_id=notification.notification_id,
                reason=reason,
            ).info("notification delivered and acknowledged")

        mark_stage("cleanup")
        if expired_hold_until is not None:
            await self._store.release_hold_if_unchanged(
                user_id, expired_hold_until, now=self._clock()
            )
        await self._store.clear_immediate_due_if_empty_and_lock_owned(
            user_id, token, now=self._clock()
        )
        return badge_refresh_needed

    async def complete_flow(self, user_id: int) -> None:
        """Release the update-entry flow generation for durable worker delivery."""
        captured = self._flow_generation_context.get()
        if captured is None or captured[0] != user_id or captured[1] is None:
            return
        await self._release_flow_generation(user_id, captured[1])

    async def complete_current_flow(self, user_id: int) -> None:
        """Release the current hold for background flows that own current FSM state."""
        observed_hold = await self._store.hold_snapshot(user_id)
        if observed_hold is None:
            return
        await self._release_flow_generation(user_id, observed_hold[1])

    async def _release_flow_generation(
        self, user_id: int, observed_generation: int
    ) -> None:
        if not await self._store.release_hold_generation_if_unchanged(
            user_id, observed_generation, now=self._clock()
        ):
            return
        logger.bind(event="notification_hold_released", user_id=user_id).info(
            "notification hold released for worker delivery"
        )

    async def _acknowledge_after_lease_loss(
        self, user_id: int, notification: BlockchainNotification
    ) -> bool:
        """Avoid a known successful Telegram send being retried when ownership changed."""
        token = self._token_factory()
        if not await self._store.acquire_lock(user_id, token):
            return False
        acknowledged = False
        try:
            acknowledged = await self._store.acknowledge_if_lock_owned(
                user_id, notification, token
            )
        finally:
            await self._store.release_lock(user_id, token)
        if acknowledged:
            await self._refresh_badge(user_id)
        return acknowledged

    async def _flush_with_owned_lock(
        self,
        user_id: int,
        token: str,
        *,
        ignore_hold: bool = False,
        reason: str,
    ) -> None:
        """Keep an owned lease alive only for the duration of this flush."""
        lease_lost = asyncio.Event()
        ownership_deadline = time.monotonic() + self._lock_lifetime_seconds
        heartbeat = asyncio.create_task(
            self._heartbeat_lock(
                user_id, token, lease_lost, ownership_deadline=ownership_deadline
            ),
            name=f"notification-lock-heartbeat-{user_id}",
        )
        progress: dict[str, object] = {
            "stage": "starting",
            "notification_id": None,
        }
        badge_refresh_needed = False
        try:
            try:
                async with asyncio.timeout(self._lock_lifetime_seconds):
                    badge_refresh_needed = await self._flush_owned(
                        user_id,
                        token,
                        ignore_hold=ignore_hold,
                        reason=reason,
                        lease_lost=lease_lost,
                        progress=progress,
                    )
            except TimeoutError:
                logger.bind(
                    event="notification_flush_timed_out",
                    user_id=user_id,
                    reason=reason,
                    stage=progress["stage"],
                    notification_id=progress["notification_id"],
                    timeout_seconds=self._lock_lifetime_seconds,
                ).warning(
                    "notification flush ownership budget expired; "
                    f"unacknowledged queue head retained: user_id={user_id} "
                    f"reason={reason} stage={progress['stage']} "
                    f"notification_id={progress['notification_id']} "
                    f"timeout_seconds={self._lock_lifetime_seconds:g}"
                )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            released = await self._store.release_lock(user_id, token)
            release_log = logger.bind(
                event="notification_flush_lock_released",
                user_id=user_id,
                reason=reason,
                released=released,
            )
            message = (
                f"notification flush lock release completed: user_id={user_id} "
                f"reason={reason} released={released}"
            )
            if released:
                release_log.debug(message)
            else:
                release_log.warning(message)
        if badge_refresh_needed is True:
            await self._refresh_badge(user_id)

    async def _heartbeat_lock(
        self,
        user_id: int,
        token: str,
        lease_lost: asyncio.Event,
        *,
        ownership_deadline: float,
    ) -> None:
        """Renew an owned lock until the bounded flush lifecycle ends."""
        try:
            while True:
                remaining = ownership_deadline - time.monotonic()
                if remaining <= 0:
                    lease_lost.set()
                    logger.bind(
                        event="notification_flush_heartbeat_deadline_reached",
                        user_id=user_id,
                    ).warning(
                        "notification lock heartbeat stopped at ownership deadline"
                    )
                    return
                await asyncio.sleep(min(self._heartbeat_interval, remaining))
                if time.monotonic() >= ownership_deadline:
                    continue
                if await self._store.renew_lock(user_id, token):
                    continue
                lease_lost.set()
                logger.bind(
                    event="notification_flush_lock_lost", user_id=user_id
                ).warning("notification flush stopped after lock ownership was lost")
                return
        except asyncio.CancelledError:
            raise
        except Exception:
            lease_lost.set()
            logger.bind(
                event="notification_flush_heartbeat_failed", user_id=user_id
            ).exception("notification lock heartbeat failed")

    async def _refresh_badge(self, user_id: int) -> None:
        try:
            async with asyncio.timeout(self._badge_timeout_seconds):
                await self._badge_refresher.refresh(user_id)
        except TimeoutError:
            logger.bind(
                event="notification_badge_refresh_timed_out",
                user_id=user_id,
                stage="badge",
                timeout_seconds=self._badge_timeout_seconds,
            ).warning("notification badge refresh timed out")
        except Exception:
            logger.bind(
                event="notification_badge_refresh_failed", user_id=user_id
            ).exception("notification badge refresh failed")

    async def _hold_allows_flush(self, user_id: int) -> tuple[bool, int | None]:
        """Return whether delivery may proceed and an expired deadline to clean."""
        hold_until = await self._store.hold_until(user_id)
        if hold_until is None:
            return True, None
        if hold_until > self._clock():
            return False, None
        return True, hold_until


def _unix_time() -> int:
    return int(time.time())


def _new_token() -> str:
    return uuid.uuid4().hex
