"""Coordinate delayed, ordered blockchain notification delivery."""

import asyncio
from contextlib import suppress
import time
import uuid
from collections.abc import Callable
from typing import Protocol

from loguru import logger

from core.models.blockchain_notification import BlockchainNotification
from infrastructure.services.telegram_delivery_service import NotificationSender


COMPLETION_LOCK_RETRY_ATTEMPTS = 3


class NotificationStore(Protocol):
    """The narrow persistence boundary needed by notification delivery."""

    async def touch(self, user_id: int, *, now: int) -> int: ...

    async def release_hold_if_unchanged(
        self, user_id: int, expected_hold_until: int, *, now: int
    ) -> bool: ...

    async def hold_until(self, user_id: int) -> int | None: ...

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
        self._store = store
        self._sender = sender
        self._badge_refresher = badge_refresher
        self._clock = clock or _unix_time
        self._token_factory = token_factory or _new_token
        self._heartbeat_interval = selected_heartbeat_interval

    async def touch(self, user_id: int) -> int:
        """Start or extend the user's sliding activity hold."""
        hold_until = await self._store.touch(user_id, now=self._clock())
        logger.bind(event="notification_hold_touched", user_id=user_id).info(
            "notification hold touched"
        )
        return hold_until

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
                event="notification_flush_lock_unavailable", user_id=user_id
            ).info("notification flush skipped because lock is owned")
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
    ) -> None:
        """Flush with an already-held lock, rechecking the hold per item."""
        expired_hold_until: int | None = None
        if not ignore_hold:
            can_flush, expired_hold_until = await self._hold_allows_flush(user_id)
            if not can_flush:
                logger.bind(
                    event="notification_flush_held", user_id=user_id, reason=reason
                ).info("notification flush deferred by active hold")
                return

        while notification := await self._store.peek(user_id):
            if lease_lost is not None and lease_lost.is_set():
                return
            if not await self._store.renew_lock(user_id, token):
                logger.bind(
                    event="notification_flush_lock_lost", user_id=user_id, reason=reason
                ).warning("notification flush stopped after lock ownership was lost")
                return

            if not ignore_hold:
                can_flush, observed_expired_hold = await self._hold_allows_flush(
                    user_id
                )
                if not can_flush:
                    logger.bind(
                        event="notification_flush_held", user_id=user_id, reason=reason
                    ).info("notification flush deferred by renewed hold")
                    return
                if observed_expired_hold is not None:
                    expired_hold_until = observed_expired_hold

            if lease_lost is not None and lease_lost.is_set():
                return

            try:
                await self._sender.send_notification(notification)
            except Exception:
                logger.bind(
                    event="notification_delivery_failed",
                    user_id=user_id,
                    notification_id=notification.notification_id,
                    reason=reason,
                ).exception("notification delivery failed; queue head retained")
                return

            if lease_lost is not None and lease_lost.is_set():
                await self._acknowledge_after_lease_loss(user_id, notification)
                return
            if not await self._store.acknowledge_if_lock_owned(
                user_id, notification, token
            ):
                logger.bind(
                    event="notification_acknowledgement_lost",
                    user_id=user_id,
                    notification_id=notification.notification_id,
                    reason=reason,
                ).warning("notification acknowledgement did not match queue head")
                return

            await self._refresh_badge(user_id)
            logger.bind(
                event="notification_delivered",
                user_id=user_id,
                notification_id=notification.notification_id,
                reason=reason,
            ).info("notification delivered and acknowledged")

        if expired_hold_until is not None:
            await self._store.release_hold_if_unchanged(
                user_id, expired_hold_until, now=self._clock()
            )
        await self._store.clear_immediate_due_if_empty_and_lock_owned(
            user_id, token, now=self._clock()
        )

    async def complete_flow(self, user_id: int) -> None:
        """Release and flush only the locked flow generation that completed."""
        observed_hold_until = await self._store.hold_until(user_id)
        if observed_hold_until is None:
            return
        token = self._token_factory()
        for attempt in range(COMPLETION_LOCK_RETRY_ATTEMPTS):
            if await self._store.acquire_lock(user_id, token):
                break
            if attempt + 1 == COMPLETION_LOCK_RETRY_ATTEMPTS:
                return
            await asyncio.sleep(0)
        release_lock = True
        try:
            if not await self._store.release_hold_if_unchanged(
                user_id, observed_hold_until, now=self._clock()
            ):
                return
            logger.bind(event="notification_hold_released", user_id=user_id).info(
                "notification hold released for completed flow"
            )
            release_lock = False
            await self._flush_with_owned_lock(user_id, token, reason="flow_completed")
        finally:
            if release_lock:
                await self._store.release_lock(user_id, token)

    async def _acknowledge_after_lease_loss(
        self, user_id: int, notification: BlockchainNotification
    ) -> None:
        """Avoid a known successful Telegram send being retried when ownership changed."""
        token = self._token_factory()
        if not await self._store.acquire_lock(user_id, token):
            return
        try:
            if await self._store.acknowledge_if_lock_owned(
                user_id, notification, token
            ):
                await self._refresh_badge(user_id)
        finally:
            await self._store.release_lock(user_id, token)

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
        heartbeat = asyncio.create_task(
            self._heartbeat_lock(user_id, token, lease_lost),
            name=f"notification-lock-heartbeat-{user_id}",
        )
        try:
            await self._flush_owned(
                user_id,
                token,
                ignore_hold=ignore_hold,
                reason=reason,
                lease_lost=lease_lost,
            )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            await self._store.release_lock(user_id, token)

    async def _heartbeat_lock(
        self, user_id: int, token: str, lease_lost: asyncio.Event
    ) -> None:
        """Renew an owned lock until the bounded flush lifecycle ends."""
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)
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
            await self._badge_refresher.refresh(user_id)
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
