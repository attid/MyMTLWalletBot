"""Automatic Horizon failover: endpoint pool, cooldowns and per-call retries.

Contract (see ``docs/exec-plans/active/2026-11-13-horizon-failover.md``):

- Failover triggers **only** on transport errors/timeouts, HTTP ``>= 500`` and
  HTTP ``429``. Business errors (HTTP 400/404: ``tx_bad_seq``,
  ``op_underfunded``, account not found) never switch endpoints.
- Every endpoint is tried once per call, at most ``max_attempts`` tries and
  within ``budget_seconds``.
- An endpoint that failed is parked in cooldown (429 base is longer than
  transport/5xx base, consecutive failures double it up to a cap).
- When every endpoint is in cooldown the call fails fast without touching the
  network and the all-down backoff escalates across consecutive calls
  (1s -> 5s -> 15s -> 60s), so we never hammer a node in a loop.
- State lives in memory: a restart forgets everything and starts from primary.
- There is no manual switch command; the admin only learns about switches from
  notifications (see ``horizon_alerts.py``) and structured logs.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, TypeVar

import aiohttp
from loguru import logger
from stellar_sdk import AiohttpClient
from stellar_sdk.exceptions import ConnectionError as HorizonConnectionError

from other.config_reader import READ_ONLY_ENDPOINT_SUFFIX, config

T = TypeVar("T")

ENDPOINT_ROLE_READ = "ro"
ENDPOINT_ROLE_WRITE = "rw"

# Backoff (seconds) applied when a whole round of endpoints is rate limited.
ALL_DOWN_BACKOFF_SCHEDULE: Final[tuple[float, ...]] = (1.0, 5.0, 15.0, 60.0)


class FailoverReason(StrEnum):
    """Why an endpoint was considered broken."""

    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    UNREACHABLE = "unreachable"


class HorizonEventKind(StrEnum):
    SWITCH = "switch"
    ALL_DOWN = "all_down"
    FREEZE = "freeze"
    RECOVERY = "recovery"


class HorizonUnavailableError(RuntimeError):
    """Every endpoint is in cooldown; no request was made."""


@dataclass(frozen=True)
class HorizonEvent:
    """A pool event worth telling the admin about."""

    kind: HorizonEventKind
    role: str
    from_url: str | None = None
    to_url: str | None = None
    reason: FailoverReason | None = None
    http_status: int | None = None
    attempt: int | None = None
    switches: int = 0
    backoff_seconds: float | None = None


HorizonNotifier = Callable[[HorizonEvent], Awaitable[None]]


def classify_horizon_error(exc: BaseException) -> FailoverReason | None:
    """Map an exception to a failover reason, or ``None`` when it must not switch.

    Horizon reports a rate limit as HTTP 429, which ``stellar_sdk`` raises as
    ``BadRequestError`` (the 400-499 bucket), so the status code -- not the
    exception class -- is the discriminator. HTTP 400/404 from Horizon carry
    business results (``tx_bad_seq``, ``op_underfunded``, unknown account) and
    must reach the caller unchanged.
    """
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        if status == 429:
            return FailoverReason.RATE_LIMITED
        if status >= 500:
            return FailoverReason.SERVER_ERROR
        return None
    if isinstance(
        exc,
        (
            HorizonConnectionError,
            aiohttp.ClientError,
            asyncio.TimeoutError,
            TimeoutError,
        ),
    ):
        return FailoverReason.UNREACHABLE
    return None


def horizon_client() -> AiohttpClient:
    """Horizon HTTP client with the timeouts the failover budget is built around."""
    return AiohttpClient(
        request_timeout=config.horizon_request_timeout_seconds,
        post_timeout=config.horizon_post_timeout_seconds,
    )


@dataclass
class HorizonEndpoint:
    url: str
    supports_submit: bool = True
    down_until: float = 0.0
    failures: int = 0
    reason: FailoverReason | None = None


def parse_endpoint(raw: str) -> tuple[str, bool]:
    """Return ``(url, supports_submit)`` for one ``HORIZON_URLS`` item."""
    value = raw.strip()
    supports_submit = True
    if value.lower().endswith(READ_ONLY_ENDPOINT_SUFFIX):
        value = value[: -len(READ_ONLY_ENDPOINT_SUFFIX)].strip()
        supports_submit = False
    return value.rstrip("/"), supports_submit


class HorizonPool:
    """Priority-ordered endpoint pool with cooldowns, sticky routing and freeze."""

    def __init__(
        self,
        endpoints: Sequence[str],
        *,
        role: str = ENDPOINT_ROLE_READ,
        clock: Callable[[], float] = time.monotonic,
        rate_limit_cooldown_seconds: float = 60.0,
        server_error_cooldown_seconds: float = 30.0,
        max_cooldown_seconds: float = 600.0,
        sticky_seconds: float = 60.0,
        freeze_switch_threshold: int = 5,
        freeze_window_seconds: float = 600.0,
        max_attempts: int = 3,
        budget_seconds: float = 25.0,
        notifier: HorizonNotifier | None = None,
        all_down_backoff: Sequence[float] = ALL_DOWN_BACKOFF_SCHEDULE,
    ) -> None:
        parsed = []
        for raw in endpoints:
            url, supports_submit = parse_endpoint(raw)
            if url:
                parsed.append(HorizonEndpoint(url=url, supports_submit=supports_submit))
        if not parsed:
            raise ValueError("Horizon pool needs at least one endpoint")
        if role == ENDPOINT_ROLE_WRITE and not any(p.supports_submit for p in parsed):
            raise ValueError(
                "Horizon write pool needs at least one endpoint able to submit"
            )

        self.role = role
        self.clock = clock
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self.server_error_cooldown_seconds = server_error_cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds
        self.sticky_seconds = sticky_seconds
        self.freeze_switch_threshold = freeze_switch_threshold
        self.freeze_window_seconds = freeze_window_seconds
        self.max_attempts = max_attempts
        self.budget_seconds = budget_seconds
        self.all_down_backoff = tuple(all_down_backoff)

        self._endpoints = parsed
        self._notifier = notifier
        self._current_url = self._primary().url
        self._sticky_url: str | None = None
        self._sticky_until = 0.0
        self._frozen_until = 0.0
        self._switch_times: deque[float] = deque()
        self._incident_active = False
        self._incident_switches = 0
        self._all_down_until = 0.0
        self._all_down_step = 0
        self._all_down_notified = False

    # -- introspection -----------------------------------------------------

    @property
    def endpoints(self) -> tuple[str, ...]:
        return tuple(endpoint.url for endpoint in self._endpoints)

    @property
    def current(self) -> str:
        return self._select(self.clock()).url

    def current_url(self) -> str:
        """Endpoint to try right now (primary again once its cooldown expired)."""
        return self.current

    def next_url(self, exclude: Collection[str] = ()) -> str | None:
        """Endpoint to try right now, skipping endpoints already tried in this call.

        ``None`` means every usable endpoint of this pool was already attempted.
        """
        candidates = [
            endpoint for endpoint in self._candidates() if endpoint.url not in exclude
        ]
        if not candidates:
            return None
        return self._select(self.clock(), candidates).url

    def snapshot(self) -> dict[str, object]:
        now = self.clock()
        return {
            "role": self.role,
            "endpoints": list(self.endpoints),
            "current": self.current,
            "down": {
                endpoint.url: endpoint.reason.value
                for endpoint in self._endpoints
                if endpoint.down_until > now and endpoint.reason is not None
            },
            "incident_switches": self._incident_switches,
            "frozen": self._frozen_until > now,
        }

    # -- selection ---------------------------------------------------------

    def _candidates(self) -> list[HorizonEndpoint]:
        if self.role != ENDPOINT_ROLE_WRITE:
            return list(self._endpoints)
        return [endpoint for endpoint in self._endpoints if endpoint.supports_submit]

    def _primary(self) -> HorizonEndpoint:
        """First endpoint this pool may use (a read-only node leads no write pool)."""
        return self._candidates()[0]

    def _select(
        self, now: float, candidates: list[HorizonEndpoint] | None = None
    ) -> HorizonEndpoint:
        pool = self._candidates() if candidates is None else candidates
        healthy = [endpoint for endpoint in pool if endpoint.down_until <= now]
        if self._sticky_url is not None and self._sticky_until > now:
            sticky = next(
                (endpoint for endpoint in healthy if endpoint.url == self._sticky_url),
                None,
            )
            if sticky is not None:
                return sticky
        if self._frozen_until > now:
            frozen = next(
                (endpoint for endpoint in healthy if endpoint.url == self._current_url),
                None,
            )
            if frozen is not None:
                return frozen
        if healthy:
            return healthy[0]
        return min(
            pool, key=lambda endpoint: (endpoint.down_until, pool.index(endpoint))
        )

    def all_down(self, now: float | None = None) -> bool:
        moment = self.clock() if now is None else now
        return all(endpoint.down_until > moment for endpoint in self._candidates())

    # -- reporting ---------------------------------------------------------

    async def report_failure(
        self,
        url: str,
        reason: FailoverReason,
        *,
        operation: str = "",
        attempt: int = 1,
        http_status: int | None = None,
    ) -> bool:
        """Park the endpoint in cooldown; return True when the pool switched."""
        now = self.clock()
        endpoint = self._endpoint(url)
        # Concurrent requests can report the same dead endpoint. Count the
        # outage once, otherwise a burst of parallel failures would escalate
        # the cooldown to its cap and fabricate switch events.
        if endpoint.down_until <= now:
            endpoint.failures += 1
            base = (
                self.rate_limit_cooldown_seconds
                if reason is FailoverReason.RATE_LIMITED
                else self.server_error_cooldown_seconds
            )
            endpoint.down_until = now + min(
                base * (2 ** (endpoint.failures - 1)), self.max_cooldown_seconds
            )
            endpoint.reason = reason
        if self._sticky_url == url:
            self._sticky_url = None
            self._sticky_until = 0.0

        if self.all_down(now):
            await self.report_all_down(operation)
            return False

        target = self._select(now)
        previous = self._current_url
        if target.url == url or target.url == previous:
            # Already on the endpoint that survives this failure: not a switch.
            self._current_url = target.url
            return False

        self._current_url = target.url
        self._sticky_url = target.url
        self._sticky_until = now + self.sticky_seconds
        await self._register_switch(
            now,
            previous_url=previous,
            target_url=target.url,
            reason=reason,
            http_status=http_status,
            attempt=attempt,
            operation=operation,
        )
        return True

    async def report_success(self, url: str) -> None:
        endpoint = self._endpoint(url)
        endpoint.failures = 0
        endpoint.down_until = 0.0
        endpoint.reason = None
        self._all_down_until = 0.0
        self._all_down_step = 0
        self._all_down_notified = False
        self._current_url = endpoint.url

        primary = self._primary().url
        if endpoint.url == primary and self._incident_active:
            switches = self._incident_switches
            self._incident_active = False
            self._incident_switches = 0
            self._switch_times.clear()
            self._frozen_until = 0.0
            self._sticky_url = None
            self._sticky_until = 0.0
            await self._notify(
                HorizonEvent(
                    kind=HorizonEventKind.RECOVERY,
                    role=self.role,
                    to_url=primary,
                    switches=switches,
                )
            )

    async def report_all_down(self, operation: str = "") -> None:
        """Register an all-down round: escalate the backoff, alert once.

        Requests fail fast while the whole pool is in cooldown, so this is the
        call that makes the 1s -> 5s -> 15s -> 60s schedule actually escalate.
        """
        now = self.clock()
        if self._all_down_until <= now:
            index = min(self._all_down_step, len(self.all_down_backoff) - 1)
            delay = self.all_down_backoff[index]
            self._all_down_step = min(
                self._all_down_step + 1, len(self.all_down_backoff) - 1
            )
            self._all_down_until = now + delay
            logger.bind(
                event="horizon_failover",
                stage="all_down",
                pool=self.role,
                operation=operation,
                backoff_seconds=delay,
            ).warning("Horizon pool is fully in cooldown")

        if self._all_down_notified:
            return
        self._all_down_notified = True
        await self._notify(
            HorizonEvent(
                kind=HorizonEventKind.ALL_DOWN,
                role=self.role,
                from_url=self._current_url,
                backoff_seconds=max(0.0, self._all_down_until - now),
            )
        )

    # -- internals ---------------------------------------------------------

    def _endpoint(self, url: str) -> HorizonEndpoint:
        for endpoint in self._endpoints:
            if endpoint.url == url:
                return endpoint
        raise KeyError(f"Unknown horizon endpoint: {url}")

    async def _register_switch(
        self,
        now: float,
        *,
        previous_url: str,
        target_url: str,
        reason: FailoverReason,
        http_status: int | None,
        attempt: int,
        operation: str,
    ) -> None:
        self._switch_times.append(now)
        while (
            self._switch_times
            and self._switch_times[0] < now - self.freeze_window_seconds
        ):
            self._switch_times.popleft()

        first_switch_of_incident = not self._incident_active
        self._incident_active = True
        self._incident_switches += 1

        freeze = (
            len(self._switch_times) > self.freeze_switch_threshold
            and self._frozen_until <= now
        )
        if freeze:
            self._frozen_until = now + self.freeze_window_seconds

        if first_switch_of_incident:
            await self._notify(
                HorizonEvent(
                    kind=HorizonEventKind.SWITCH,
                    role=self.role,
                    from_url=previous_url,
                    to_url=target_url,
                    reason=reason,
                    http_status=http_status,
                    attempt=attempt,
                    switches=self._incident_switches,
                )
            )
        if freeze:
            logger.bind(
                event="horizon_failover",
                stage="freeze",
                pool=self.role,
                operation=operation,
                switches=len(self._switch_times),
            ).error("Horizon failover freeze: too many switches in the window")
            await self._notify(
                HorizonEvent(
                    kind=HorizonEventKind.FREEZE,
                    role=self.role,
                    from_url=previous_url,
                    to_url=target_url,
                    switches=len(self._switch_times),
                )
            )

    async def _notify(self, event: HorizonEvent) -> None:
        if self._notifier is None:
            return
        try:
            await self._notifier(event)
        except Exception as exc:  # notifications must never break a request
            logger.bind(
                event="horizon_failover",
                stage="notify_failed",
                pool=self.role,
                error=str(exc),
            ).warning("Horizon failover notification failed")


async def with_horizon_failover(
    role: str,
    operation: str,
    call: Callable[[str], Awaitable[T]],
    *,
    pool: HorizonPool | None = None,
) -> T:
    """Run ``call(url)`` with endpoint failover.

    ``call`` receives an endpoint URL and must create its own client, so a retry
    never reuses a client bound to the failed endpoint.
    """
    current_pool = pool or get_horizon_pool(role)
    deadline = current_pool.clock() + current_pool.budget_seconds
    attempts = 0
    tried_urls: set[str] = set()
    last_error: BaseException | None = None

    while attempts < current_pool.max_attempts:
        if attempts and current_pool.clock() >= deadline:
            logger.bind(
                event="horizon_failover",
                stage="budget_exhausted",
                pool=role,
                operation=operation,
                attempts=attempts,
            ).warning("Horizon failover budget exhausted")
            break
        if current_pool.all_down():
            await current_pool.report_all_down(operation)
            break
        url = current_pool.next_url(tried_urls)
        if url is None:
            break
        tried_urls.add(url)
        attempts += 1
        started = current_pool.clock()
        try:
            result = await call(url)
        except Exception as exc:
            reason = classify_horizon_error(exc)
            if reason is None:
                raise
            last_error = exc
            status = getattr(exc, "status", None)
            logger.bind(
                event="horizon_failover",
                stage="attempt_failed",
                pool=role,
                operation=operation,
                url=url,
                reason=reason.value,
                http_status=status,
                attempt=attempts,
                elapsed_ms=round((current_pool.clock() - started) * 1000),
                error=str(exc)[:500],
            ).warning("Horizon endpoint failed")
            await current_pool.report_failure(
                url,
                reason,
                operation=operation,
                attempt=attempts,
                http_status=status,
            )
            continue

        await current_pool.report_success(url)
        if attempts > 1:
            logger.bind(
                event="horizon_failover",
                stage="attempt_succeeded",
                pool=role,
                operation=operation,
                url=url,
                attempts=attempts,
                elapsed_ms=round((current_pool.clock() - started) * 1000),
            ).info("Horizon request succeeded after failover")
        return result

    if last_error is not None:
        raise last_error
    raise HorizonUnavailableError(
        f"Horizon pool '{role}' is in cooldown; request was not sent"
    )


_pools: dict[str, HorizonPool] = {}
_notifier: HorizonNotifier | None = None


def build_horizon_pool(role: str) -> HorizonPool:
    """Create a pool from the current config (``horizon_endpoints``)."""
    return HorizonPool(
        config.horizon_endpoints,
        role=role,
        rate_limit_cooldown_seconds=config.horizon_rate_limit_cooldown_seconds,
        server_error_cooldown_seconds=config.horizon_server_error_cooldown_seconds,
        max_cooldown_seconds=config.horizon_max_cooldown_seconds,
        sticky_seconds=config.horizon_sticky_seconds,
        freeze_switch_threshold=config.horizon_freeze_switch_threshold,
        freeze_window_seconds=config.horizon_freeze_window_seconds,
        max_attempts=config.horizon_failover_max_attempts,
        budget_seconds=config.horizon_failover_budget_seconds,
        notifier=_notifier,
    )


def get_horizon_pool(role: str = ENDPOINT_ROLE_READ) -> HorizonPool:
    """Per-process pool for ``ro`` (reads) or ``rw`` (submission)."""
    pool = _pools.get(role)
    if pool is None:
        pool = build_horizon_pool(role)
        _pools[role] = pool
    return pool


def reset_horizon_pools() -> None:
    """Drop all pool state (restart semantics; used by tests)."""
    _pools.clear()


def setup_horizon_pools(notifier: HorizonNotifier | None = None) -> None:
    """Wire the admin notifier and eagerly build both pools at startup."""
    global _notifier
    _notifier = notifier
    reset_horizon_pools()
    get_horizon_pool(ENDPOINT_ROLE_READ)
    get_horizon_pool(ENDPOINT_ROLE_WRITE)
