import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from loguru import logger

from middleware.db import DbSessionMiddleware


class TrackingSessionPool:
    def __init__(self) -> None:
        self.active_sessions = 0

    @asynccontextmanager
    async def get_session(self):
        self.active_sessions += 1
        try:
            yield object()
        finally:
            self.active_sessions -= 1


@pytest.mark.asyncio
async def test_long_handler_is_warned_about_without_being_cancelled() -> None:
    pool = TrackingSessionPool()
    middleware = DbSessionMiddleware(
        pool,
        MagicMock(),
        handler_warning_seconds=0.01,
    )
    started = asyncio.Event()
    release = asyncio.Event()
    cancelled = asyncio.Event()

    async def long_handler(_event, _data):
        started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "done"

    records = []
    sink_id = logger.add(lambda message: records.append(message.record), level="WARNING")
    task = asyncio.create_task(
        middleware(long_handler, SimpleNamespace(from_user=None), {})
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=0.1)
        await asyncio.sleep(0.03)

        assert not task.done()
        assert not cancelled.is_set()
        assert any(
            record["extra"].get("event") == "telegram_update_running_long"
            for record in records
        )

        release.set()
        assert await asyncio.wait_for(task, timeout=0.2) == "done"
    finally:
        logger.remove(sink_id)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    assert pool.active_sessions == 0
