from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import infrastructure.workers.message_worker as message_worker
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


class QueueSession:
    def __init__(self, messages: list[object]) -> None:
        self._messages = messages
        self.commits = 0

    async def execute(self, _statement: object):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: self._messages)
        )

    async def commit(self) -> None:
        self.commits += 1


class TrackingDbPool:
    def __init__(self, messages: list[object]) -> None:
        self.active_sessions = 0
        self.opened_sessions: list[QueueSession] = []
        self._messages = messages

    @asynccontextmanager
    async def get_session(self):
        session = QueueSession(self._messages if not self.opened_sessions else [])
        self.opened_sessions.append(session)
        self.active_sessions += 1
        try:
            yield session
        finally:
            self.active_sessions -= 1


class FakeStorage:
    async def update_data(self, **_kwargs) -> None:
        return None


@pytest.mark.asyncio
async def test_message_worker_releases_read_session_before_external_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued_message = SimpleNamespace(
        message_id=17,
        user_id=42,
        user_message="queued",
    )
    db_pool = TrackingDbPool([queued_message])
    active_during_send: list[int] = []

    async def send_message(*_args, **_kwargs) -> None:
        active_during_send.append(db_pool.active_sessions)

    monkeypatch.setattr(message_worker, "cmd_info_message", send_message)
    app_context = SimpleNamespace(
        db_pool=db_pool,
        bot=SimpleNamespace(id=1),
        dispatcher=SimpleNamespace(storage=FakeStorage()),
        bot_health_service=None,
    )

    await cmd_send_message_1m(app_context)

    assert active_during_send == [0]
    assert db_pool.active_sessions == 0
    assert len(db_pool.opened_sessions) == 2
    assert db_pool.opened_sessions[1].commits == 1
