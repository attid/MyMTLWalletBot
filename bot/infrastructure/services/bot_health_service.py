"""Functional health checks for the bot container."""

import asyncio
from dataclasses import dataclass
import time
from typing import Any, Callable

from sqlalchemy import text


@dataclass(frozen=True)
class BotHealthReport:
    """Serializable result of the bot's functional health checks."""

    healthy: bool
    checks: dict[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.healthy else "unhealthy",
            "checks": self.checks,
        }


class BotHealthService:
    """Detect a stale scheduler and an unavailable database."""

    def __init__(
        self,
        *,
        db_pool: Any,
        clock: Callable[[], float] | None = None,
        startup_grace_seconds: float = 60,
        scheduler_stale_seconds: float = 60,
        database_timeout_seconds: float = 5,
    ) -> None:
        self._db_pool = db_pool
        self._clock = clock or time.monotonic
        self._startup_grace_seconds = startup_grace_seconds
        self._scheduler_stale_seconds = scheduler_stale_seconds
        self._database_timeout_seconds = database_timeout_seconds
        self._started_at = self._clock()
        self._scheduler_started_at: float | None = None
        self._scheduler_completed_at: float | None = None

    def mark_scheduler_started(self) -> None:
        self._scheduler_started_at = self._clock()

    def mark_scheduler_completed(self) -> None:
        self._scheduler_started_at = None
        self._scheduler_completed_at = self._clock()

    async def check(self) -> BotHealthReport:
        scheduler = self._scheduler_status()
        database = await self._database_status()
        return BotHealthReport(
            healthy=scheduler in {"ok", "starting", "running", "running_long"}
            and database == "ok",
            checks={"scheduler": scheduler, "database": database},
        )

    def _scheduler_status(self) -> str:
        now = self._clock()
        if self._scheduler_started_at is not None:
            if now - self._scheduler_started_at > self._scheduler_stale_seconds:
                return "running_long"
            return "running"
        if self._scheduler_completed_at is not None:
            if now - self._scheduler_completed_at > self._scheduler_stale_seconds:
                return "stale"
            return "ok"
        if now - self._started_at > self._startup_grace_seconds:
            return "not_started"
        return "starting"

    async def _database_status(self) -> str:
        try:
            async with asyncio.timeout(self._database_timeout_seconds):
                async with self._db_pool.get_session() as session:
                    await session.execute(text("SELECT 1 FROM RDB$DATABASE"))
        except TimeoutError:
            return "timeout"
        except Exception:
            return "error"
        return "ok"
