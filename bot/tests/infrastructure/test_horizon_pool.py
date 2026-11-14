"""Unit tests for the Horizon failover pool state machine."""

import asyncio
import json

import pytest
from stellar_sdk.exceptions import (
    BadRequestError,
    BadResponseError,
    ConnectionError,
    Response,
)

from infrastructure.services.horizon_pool import (
    FailoverReason,
    HorizonEventKind,
    HorizonPool,
    HorizonUnavailableError,
    classify_horizon_error,
    with_horizon_failover,
)


A = "https://a.example"
B = "https://b.example"
C = "https://c.example"
D = "https://d.example"


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_pool(*endpoints: str, clock: FakeClock | None = None, **kwargs) -> HorizonPool:
    fake_clock = clock or FakeClock()
    kwargs.setdefault("clock", fake_clock)
    return HorizonPool(list(endpoints) or [A, B, C], **kwargs)


def rate_limit_error() -> BadRequestError:
    return BadRequestError(
        Response(429, json.dumps({"title": "Too Many Requests"}), {}, A)
    )


def server_error() -> BadResponseError:
    return BadResponseError(Response(503, "{}", {}, A))


def business_error() -> BadRequestError:
    return BadRequestError(
        Response(
            400,
            json.dumps({"extras": {"result_codes": {"transaction": "tx_bad_seq"}}}),
            {},
            A,
        )
    )


def test_pool_starts_at_primary() -> None:
    pool = make_pool()
    assert pool.current_url() == A
    assert pool.all_down() is False


def test_read_only_endpoint_is_excluded_from_write_pool() -> None:
    pool = HorizonPool([A, f"{B}|ro"], role="rw")
    assert pool.endpoints == (A, B)
    assert pool.current_url() == A

    asyncio.run(pool.report_failure(A, FailoverReason.RATE_LIMITED))
    assert pool.current_url() == A  # B is read-only, nothing else to switch to


def test_read_only_only_write_pool_is_rejected() -> None:
    with pytest.raises(ValueError):
        HorizonPool([f"{A}|ro"], role="rw")


def test_failure_switches_to_next_endpoint_and_keeps_endpoint_healthy() -> None:
    pool = make_pool()

    switched = asyncio.run(pool.report_failure(A, FailoverReason.RATE_LIMITED))

    assert switched is True
    assert pool.current_url() == B
    assert pool.all_down() is False


def test_rate_limit_cooldown_grows_twice_per_failure_and_caps() -> None:
    clock = FakeClock()
    pool = make_pool(
        A,
        clock=clock,
        rate_limit_cooldown_seconds=60.0,
        max_cooldown_seconds=600.0,
    )

    expected = [60.0, 120.0, 240.0, 480.0, 600.0]
    for cooldown in expected:
        asyncio.run(pool.report_failure(A, FailoverReason.RATE_LIMITED))
        assert pool.snapshot()["down"][A] == FailoverReason.RATE_LIMITED.value
        clock.advance(0)
        endpoint = next(e for e in pool._endpoints if e.url == A)
        assert endpoint.down_until == clock.now + cooldown
        clock.advance(cooldown + 1)


def test_transport_error_uses_shorter_base_cooldown() -> None:
    clock = FakeClock()
    pool = make_pool(A, clock=clock)

    asyncio.run(pool.report_failure(A, FailoverReason.UNREACHABLE))

    endpoint = next(e for e in pool._endpoints if e.url == A)
    assert endpoint.down_until == clock.now + 30.0


def test_lazy_return_to_primary_after_cooldown() -> None:
    clock = FakeClock()
    pool = make_pool(clock=clock)
    asyncio.run(pool.report_failure(A, FailoverReason.RATE_LIMITED))
    assert pool.current_url() == B

    clock.advance(61)

    assert pool.current_url() == A


def test_sticky_keeps_selected_endpoint_for_sticky_window() -> None:
    clock = FakeClock()
    pool = make_pool(clock=clock, sticky_seconds=60.0)
    asyncio.run(pool.report_failure(A, FailoverReason.SERVER_ERROR))

    clock.advance(31)  # A's 30s cooldown expired, sticky still active
    assert pool.current_url() == B

    clock.advance(30)
    assert pool.current_url() == A


def test_all_down_reports_once_and_escalates_backoff() -> None:
    clock = FakeClock()
    events: list = []

    async def notifier(event) -> None:
        events.append(event)

    pool = make_pool(A, B, clock=clock, notifier=notifier)

    for url in (A, B):
        asyncio.run(pool.report_failure(url, FailoverReason.RATE_LIMITED))

    assert pool.all_down() is True
    assert [e.kind for e in events] == [
        HorizonEventKind.SWITCH,
        HorizonEventKind.ALL_DOWN,
    ]
    assert pool._all_down_until > clock.now

    asyncio.run(pool.report_all_down("test"))
    assert len(events) == 2  # deduplicated inside the episode


def test_single_endpoint_pool_never_switches() -> None:
    pool = make_pool(A)

    switched = asyncio.run(pool.report_failure(A, FailoverReason.RATE_LIMITED))

    assert switched is False
    assert pool.all_down() is True


def test_freeze_after_too_many_switches_in_window() -> None:
    clock = FakeClock()
    events: list = []

    async def notifier(event) -> None:
        events.append(event)

    pool = make_pool(
        A,
        B,
        C,
        D,
        clock=clock,
        notifier=notifier,
        freeze_switch_threshold=2,
        freeze_window_seconds=600.0,
    )

    for url in (A, B, C):
        asyncio.run(pool.report_failure(url, FailoverReason.SERVER_ERROR))

    assert pool.snapshot()["frozen"] is True
    assert HorizonEventKind.FREEZE in [e.kind for e in events]
    # Frozen pool keeps the current endpoint even after primary recovers.
    clock.advance(61)
    assert pool.current_url() == D


def test_recovery_event_only_when_primary_answers_again() -> None:
    clock = FakeClock()
    events: list = []

    async def notifier(event) -> None:
        events.append(event)

    pool = make_pool(A, B, clock=clock, notifier=notifier)
    asyncio.run(pool.report_failure(A, FailoverReason.RATE_LIMITED))
    assert [e.kind for e in events] == [HorizonEventKind.SWITCH]

    asyncio.run(pool.report_success(B))
    assert [e.kind for e in events] == [HorizonEventKind.SWITCH]

    clock.advance(61)
    asyncio.run(pool.report_success(A))
    assert [e.kind for e in events] == [
        HorizonEventKind.SWITCH,
        HorizonEventKind.RECOVERY,
    ]
    assert events[-1].switches == 1


def test_switch_between_non_primary_endpoints_is_deduped_per_incident() -> None:
    clock = FakeClock()
    events: list = []

    async def notifier(event) -> None:
        events.append(event)

    pool = make_pool(A, B, C, clock=clock, notifier=notifier, sticky_seconds=60.0)

    asyncio.run(pool.report_failure(A, FailoverReason.SERVER_ERROR))
    asyncio.run(pool.report_failure(B, FailoverReason.SERVER_ERROR))

    assert [e.kind for e in events] == [HorizonEventKind.SWITCH]
    assert events[0].from_url == A
    assert events[0].to_url == B
    assert pool.snapshot()["incident_switches"] == 2


def test_classification_of_horizon_errors() -> None:
    assert classify_horizon_error(rate_limit_error()) is FailoverReason.RATE_LIMITED
    assert classify_horizon_error(server_error()) is FailoverReason.SERVER_ERROR
    assert classify_horizon_error(ConnectionError("boom")) is FailoverReason.UNREACHABLE
    assert classify_horizon_error(asyncio.TimeoutError()) is FailoverReason.UNREACHABLE


def test_business_errors_never_trigger_failover() -> None:
    assert classify_horizon_error(business_error()) is None
    assert classify_horizon_error(ValueError("unrelated")) is None


@pytest.mark.asyncio
async def test_with_horizon_failover_retries_on_next_endpoint() -> None:
    pool = make_pool(A, B, C)
    calls: list[str] = []

    async def call(url: str) -> str:
        calls.append(url)
        if url == A:
            raise rate_limit_error()
        return "ok"

    assert await with_horizon_failover("ro", "op", call, pool=pool) == "ok"
    assert calls == [A, B]


@pytest.mark.asyncio
async def test_with_horizon_failover_does_not_retry_business_errors() -> None:
    pool = make_pool(A, B, C)
    calls: list[str] = []

    async def call(url: str) -> str:
        calls.append(url)
        raise business_error()

    with pytest.raises(BadRequestError):
        await with_horizon_failover("ro", "op", call, pool=pool)

    assert calls == [A]


@pytest.mark.asyncio
async def test_with_horizon_failover_stops_at_budget() -> None:
    clock = FakeClock()
    pool = make_pool(A, B, C, clock=clock, budget_seconds=5.0)
    calls: list[str] = []

    async def call(url: str) -> str:
        calls.append(url)
        clock.advance(4)
        raise server_error()

    with pytest.raises(BadResponseError):
        await with_horizon_failover("ro", "op", call, pool=pool)

    assert calls == [A, B]


@pytest.mark.asyncio
async def test_with_horizon_failover_fails_fast_when_pool_is_down() -> None:
    pool = make_pool(A)

    async def call(url: str) -> str:
        raise AssertionError("network call must not happen while pool is down")

    await pool.report_failure(A, FailoverReason.RATE_LIMITED)

    with pytest.raises(HorizonUnavailableError):
        await with_horizon_failover("ro", "op", call, pool=pool)


@pytest.mark.asyncio
async def test_write_pool_primary_skips_read_only_node_and_reports_recovery() -> None:
    """A ``|ro`` node must not become the primary of the write pool."""
    clock = FakeClock()
    events: list = []

    async def notifier(event) -> None:
        events.append(event)

    pool = HorizonPool([f"{A}|ro", B, C], role="rw", clock=clock, notifier=notifier)

    assert pool.current_url() == B

    assert await pool.report_failure(B, FailoverReason.RATE_LIMITED) is True
    assert pool.current_url() == C
    assert [e.kind for e in events] == [HorizonEventKind.SWITCH]

    clock.advance(61)
    await pool.report_success(B)

    assert [e.kind for e in events] == [
        HorizonEventKind.SWITCH,
        HorizonEventKind.RECOVERY,
    ]
    assert events[-1].to_url == B


@pytest.mark.asyncio
async def test_concurrent_failures_of_one_endpoint_count_once() -> None:
    """A burst of parallel failures must not fake switches or freeze the pool."""
    clock = FakeClock()
    events: list = []

    async def notifier(event) -> None:
        events.append(event)

    pool = make_pool(clock=clock, notifier=notifier, freeze_switch_threshold=2)

    await asyncio.gather(
        *(pool.report_failure(A, FailoverReason.RATE_LIMITED) for _ in range(6))
    )

    assert [e.kind for e in events] == [HorizonEventKind.SWITCH]
    assert pool.snapshot()["incident_switches"] == 1
    assert pool.snapshot()["frozen"] is False
    assert pool._endpoint(A).failures == 1


@pytest.mark.asyncio
async def test_each_endpoint_is_tried_at_most_once_per_call() -> None:
    pool = make_pool()
    calls: list[str] = []

    async def call(url: str) -> str:
        calls.append(url)
        if url == A:
            # A concurrent request "heals" A while our call is still running.
            await pool.report_success(A)
            raise rate_limit_error()
        return "ok"

    assert await with_horizon_failover("ro", "op", call, pool=pool) == "ok"
    assert calls == [A, B]


@pytest.mark.asyncio
async def test_all_down_backoff_escalates_across_calls() -> None:
    clock = FakeClock()
    pool = make_pool(A, B, clock=clock)

    await pool.report_failure(A, FailoverReason.RATE_LIMITED)
    await pool.report_failure(B, FailoverReason.RATE_LIMITED)

    delays = []
    for _ in range(4):
        delays.append(round(pool._all_down_until - clock.now, 1))
        clock.advance(pool._all_down_until - clock.now)
        await pool.report_all_down("op")

    assert delays == [1.0, 5.0, 15.0, 60.0]


def test_not_found_is_not_a_failover_reason() -> None:
    from stellar_sdk.exceptions import NotFoundError

    assert classify_horizon_error(NotFoundError(Response(404, "{}", {}, A))) is None


@pytest.mark.asyncio
async def test_concurrent_calls_all_retry_on_the_live_endpoint() -> None:
    """Regression: the second parallel caller must not give up on a live node."""
    pool = make_pool()
    calls: list[str] = []

    async def call(url: str) -> str:
        calls.append(url)
        if url == A:
            await asyncio.sleep(0)  # let the sibling coroutines hit A as well
            raise rate_limit_error()
        return "ok"

    results = await asyncio.gather(
        *(with_horizon_failover("ro", "op", call, pool=pool) for _ in range(3))
    )

    assert results == ["ok", "ok", "ok"]
    assert calls.count(A) == 3


@pytest.mark.asyncio
async def test_escalated_backoff_does_not_block_recovered_endpoints() -> None:
    clock = FakeClock()
    pool = make_pool(A, B, clock=clock)

    await pool.report_failure(A, FailoverReason.RATE_LIMITED)
    await pool.report_failure(B, FailoverReason.RATE_LIMITED)
    # Escalate the all-down window well past the node cooldowns.
    for _ in range(3):
        clock.advance(pool._all_down_until - clock.now)
        await pool.report_all_down("op")

    clock.advance(61)
    calls: list[str] = []

    async def call(url: str) -> str:
        calls.append(url)
        return "ok"

    assert await with_horizon_failover("ro", "op", call, pool=pool) == "ok"
    assert calls == [A]
