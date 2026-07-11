"""Bounded polling for durable delayed blockchain notification delivery."""

import asyncio
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
    """Sequentially flush users whose persisted notification holds are due."""

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

    async def run(self) -> None:
        """Poll until cancelled; individual polling failures do not stop the worker."""
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.bind(event="notification_delivery_poll_failed").exception(
                    "notification delivery poll failed"
                )
            await asyncio.sleep(self._poll_interval_seconds)

    async def poll_once(self) -> None:
        """Flush one bounded batch of users whose holds have expired."""
        user_ids = await self._store.due_users(
            now=self._clock(), limit=self._batch_size
        )
        for user_id in user_ids:
            try:
                await self._coordinator.flush(user_id, reason="hold_expired")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.bind(
                    event="notification_delivery_flush_failed", user_id=user_id
                ).exception("notification delivery flush failed")


def _unix_time() -> int:
    return int(time.time())
