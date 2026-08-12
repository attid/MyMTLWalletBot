import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import pytest


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeSession:
    def __init__(self, *, block: bool = False) -> None:
        self._block = block

    async def execute(self, _statement: object) -> None:
        if self._block:
            await asyncio.Event().wait()


class FakeDbPool:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    @asynccontextmanager
    async def get_session(self):
        yield self._session


def health_service_class():
    try:
        from infrastructure.services.bot_health_service import BotHealthService
    except ModuleNotFoundError:
        pytest.fail("BotHealthService is not implemented")
    return BotHealthService


@pytest.mark.asyncio
async def test_health_is_ok_after_recent_scheduler_completion() -> None:
    clock = FakeClock()
    service = health_service_class()(
        db_pool=FakeDbPool(FakeSession()),
        clock=clock,
        startup_grace_seconds=60,
        scheduler_stale_seconds=30,
        database_timeout_seconds=0.01,
    )
    service.mark_scheduler_started()
    service.mark_scheduler_completed()
    clock.now = 10

    report = await service.check()

    assert report.healthy is True
    assert report.checks == {"scheduler": "ok", "database": "ok"}


@pytest.mark.asyncio
async def test_health_fails_when_scheduler_has_not_completed_after_grace() -> None:
    clock = FakeClock()
    service = health_service_class()(
        db_pool=FakeDbPool(FakeSession()),
        clock=clock,
        startup_grace_seconds=60,
        scheduler_stale_seconds=30,
        database_timeout_seconds=0.01,
    )
    clock.now = 61

    report = await service.check()

    assert report.healthy is False
    assert report.checks["scheduler"] == "not_started"
    assert report.checks["database"] == "ok"


@pytest.mark.asyncio
async def test_health_fails_when_scheduler_has_not_run_again() -> None:
    clock = FakeClock()
    service = health_service_class()(
        db_pool=FakeDbPool(FakeSession()),
        clock=clock,
        startup_grace_seconds=60,
        scheduler_stale_seconds=30,
        database_timeout_seconds=0.01,
    )
    service.mark_scheduler_started()
    service.mark_scheduler_completed()
    clock.now = 31

    report = await service.check()

    assert report.healthy is False
    assert report.checks["scheduler"] == "stale"


@pytest.mark.asyncio
async def test_health_stays_ok_while_scheduler_is_running_long() -> None:
    clock = FakeClock()
    service = health_service_class()(
        db_pool=FakeDbPool(FakeSession()),
        clock=clock,
        startup_grace_seconds=60,
        scheduler_stale_seconds=30,
        database_timeout_seconds=0.01,
    )
    service.mark_scheduler_started()
    clock.now = 31

    report = await service.check()

    assert report.healthy is True
    assert report.checks == {
        "scheduler": "running_long",
        "database": "ok",
    }


@pytest.mark.asyncio
async def test_health_fails_when_database_probe_times_out() -> None:
    clock = FakeClock()
    service = health_service_class()(
        db_pool=FakeDbPool(FakeSession(block=True)),
        clock=clock,
        startup_grace_seconds=60,
        scheduler_stale_seconds=30,
        database_timeout_seconds=0.01,
    )
    service.mark_scheduler_started()
    service.mark_scheduler_completed()

    report = await service.check()

    assert report.healthy is False
    assert report.checks == {"scheduler": "ok", "database": "timeout"}


def test_bot_image_has_functional_healthcheck() -> None:
    dockerfile = Path(__file__).parents[3] / "Dockerfile"
    content = dockerfile.read_text()

    assert "HEALTHCHECK --interval=30s --timeout=10s" in content
    assert "--start-period=60s --retries=3" in content
    assert "http://127.0.0.1:8081/health" in content
