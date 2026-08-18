"""Bounded polling for durable delayed blockchain notification delivery."""

import asyncio
from functools import partial
import math
import time
from collections.abc import Callable
from typing import Protocol

from loguru import logger

from infrastructure.services.notification_coordinator import NotificationCoordinator


class NotificationDueStore(Protocol):
    """Persistence operations required by the expiry poller."""

    async def due_users(self, *, now: int, limit: int) -> list[int]: ...


class NotificationDeliveryWorker:
    """Flush due users without allowing one user to block the polling loop."""

    def __init__(
        self,
        *,
        store: NotificationDueStore,
        coordinator: NotificationCoordinator,
        poll_interval_seconds: float,
        batch_size: int,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if not math.isfinite(poll_interval_seconds) or poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be finite and positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._store = store
        self._coordinator = coordinator
        self._poll_interval_seconds = poll_interval_seconds
        self._batch_size = batch_size
        self._clock = clock or _unix_time
        self._active_flushes: dict[int, asyncio.Task[None]] = {}

    async def run(self) -> None:
        """Poll until cancelled; individual polling failures do not stop the worker."""
        try:
            while True:
                poll_started = time.monotonic()
                try:
                    await self.poll_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.bind(event="notification_delivery_poll_failed").exception(
                        "notification delivery poll failed"
                    )
                elapsed = time.monotonic() - poll_started
                await asyncio.sleep(max(0.0, self._poll_interval_seconds - elapsed))
        finally:
            self._cancel_active_flushes()

    async def poll_once(self) -> None:
        """Start one bounded batch and wait briefly for ordinary flushes."""
        user_ids = await self._store.due_users(
            now=self._clock(), limit=self._batch_size + len(self._active_flushes)
        )
        available_slots = self._batch_size - len(self._active_flushes)
        started: list[asyncio.Task[None]] = []
        for user_id in user_ids:
            if user_id in self._active_flushes:
                continue
            if len(started) >= available_slots:
                break
            task = asyncio.create_task(
                self._flush_user(user_id),
                name=f"notification-delivery-{user_id}",
            )
            self._active_flushes[user_id] = task
            task.add_done_callback(partial(self._flush_done, user_id))
            started.append(task)
        if started:
            await asyncio.wait(started, timeout=self._poll_interval_seconds)

    async def _flush_user(self, user_id: int) -> None:
        try:
            await self._coordinator.flush(user_id, reason="hold_expired")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.bind(
                event="notification_delivery_flush_failed", user_id=user_id
            ).exception("notification delivery flush failed")

    def _flush_done(self, user_id: int, task: asyncio.Task[None]) -> None:
        if self._active_flushes.get(user_id) is task:
            self._active_flushes.pop(user_id, None)
        if task.cancelled():
            return
        task.exception()

    def _cancel_active_flushes(self) -> None:
        for task in tuple(self._active_flushes.values()):
            task.cancel()


def _unix_time() -> int:
    return int(time.time())
