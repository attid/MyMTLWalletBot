from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from infrastructure.workers.message_worker import cmd_send_message_1m


class EmptyScalarResult:
    def scalars(self):
        return self

    def all(self) -> list[object]:
        return []


class EmptyMessageSession:
    async def execute(self, _statement: object) -> EmptyScalarResult:
        return EmptyScalarResult()


class FakeDbPool:
    @asynccontextmanager
    async def get_session(self):
        yield EmptyMessageSession()


class TrackingHealthService:
    def __init__(self) -> None:
        self.events: list[str] = []

    def mark_scheduler_started(self) -> None:
        self.events.append("started")

    def mark_scheduler_completed(self) -> None:
        self.events.append("completed")


@pytest.mark.asyncio
async def test_message_worker_records_scheduler_completion() -> None:
    health_service = TrackingHealthService()
    app_context = SimpleNamespace(
        db_pool=FakeDbPool(),
        bot_health_service=health_service,
    )

    await cmd_send_message_1m(app_context)

    assert health_service.events == ["started", "completed"]
