"""Integration-ish check: a dead primary must not block reads or hide the switch."""

import json

import pytest
from aiohttp import web

from infrastructure.services.horizon_alerts import HorizonAdminAlerter
from infrastructure.services.horizon_pool import (
    reset_horizon_pools,
    setup_horizon_pools,
)
from other.config_reader import config
from other.stellar_tools import async_stellar_check_fee

SOME_ACCOUNT = "GCEZWKCA5VLDNRLN3RPRJMRZOX3Z6G5CHCGSNFHEYVXM3XOJMDS674JZ"


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append({"chat_id": chat_id, "text": text})


async def _start_node(handler, port: int):
    app = web.Application()
    app.router.add_get("/fee_stats", handler)
    app.router.add_get("/accounts/{account_id}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return runner


@pytest.fixture
async def two_horizons():
    """Primary answers 429, secondary answers 200."""

    hits: list[str] = []

    async def limited(request):
        hits.append("primary")
        return web.Response(
            status=429,
            text=json.dumps({"type": "rate_limit", "title": "Too Many Requests"}),
            content_type="application/json",
        )

    async def healthy(request):
        if request.path.startswith("/accounts/"):
            return web.json_response(
                {
                    "account_id": request.match_info["account_id"],
                    "sequence": "1",
                    "balances": [],
                }
            )
        return web.json_response(
            {
                "_links": {},
                "last_ledger": "1",
                "last_ledger_base_fee": "100",
                "ledger_capacity_usage": "0.1",
                "fee_charged": {
                    "max": "200",
                    "min": "100",
                    "mode": "100",
                    "p10": "100",
                    "p50": "100",
                    "p90": "100",
                    "p95": "100",
                    "p99": "100",
                },
                "max_fee": {
                    "max": "200",
                    "min": "100",
                    "mode": "100",
                    "p10": "100",
                    "p50": "100",
                    "p90": "100",
                    "p95": "100",
                    "p99": "100",
                },
            }
        )

    from tests.conftest import get_free_port

    limited_port = get_free_port()
    healthy_port = get_free_port()
    limited_runner = await _start_node(limited, limited_port)
    healthy_runner = await _start_node(healthy, healthy_port)
    try:
        yield {
            "urls": [
                f"http://127.0.0.1:{limited_port}",
                f"http://127.0.0.1:{healthy_port}",
            ],
            "hits": hits,
        }
    finally:
        await limited_runner.cleanup()
        await healthy_runner.cleanup()


@pytest.mark.asyncio
async def test_failover_switches_to_secondary_and_alerts_admin_once(two_horizons):
    urls = two_horizons["urls"]
    bot = _FakeBot()
    previous_endpoints = list(config.horizon_endpoints)
    config.horizon_endpoints = urls
    setup_horizon_pools(HorizonAdminAlerter(bot, 42).notify)
    try:
        result = await async_stellar_check_fee()
    finally:
        config.horizon_endpoints = previous_endpoints
        reset_horizon_pools()

    assert result == "100-200"
    assert len(bot.messages) == 1
    message = bot.messages[0]
    assert message["chat_id"] == 42
    assert urls[0] in message["text"]
    assert urls[1] in message["text"]
    assert message["text"].count("429") == 1


@pytest.mark.asyncio
async def test_second_call_uses_secondary_without_new_alert(two_horizons):
    bot = _FakeBot()
    previous_endpoints = list(config.horizon_endpoints)
    config.horizon_endpoints = two_horizons["urls"]
    setup_horizon_pools(HorizonAdminAlerter(bot, 42).notify)
    try:
        await async_stellar_check_fee()
        await async_stellar_check_fee()
    finally:
        config.horizon_endpoints = previous_endpoints
        reset_horizon_pools()

    assert len(bot.messages) == 1


@pytest.mark.asyncio
async def test_all_endpoints_down_raises_without_touching_network(two_horizons):
    from infrastructure.services.horizon_pool import (
        HorizonUnavailableError,
        get_horizon_pool,
    )

    previous_endpoints = list(config.horizon_endpoints)
    config.horizon_endpoints = two_horizons["urls"][:1]
    setup_horizon_pools()
    try:
        with pytest.raises(Exception):
            await async_stellar_check_fee()

        hits_after_first_call = len(two_horizons["hits"])
        pool = get_horizon_pool("ro")
        assert pool.all_down() is True

        with pytest.raises(HorizonUnavailableError):
            await async_stellar_check_fee()

        assert len(two_horizons["hits"]) == hits_after_first_call
    finally:
        config.horizon_endpoints = previous_endpoints
        reset_horizon_pools()


@pytest.mark.asyncio
async def test_stellar_service_reads_through_the_pool(two_horizons):
    """The unpinned service (real runtime wiring) must follow the failover pool."""
    from infrastructure.services.stellar_service import StellarService

    urls = two_horizons["urls"]
    bot = _FakeBot()
    previous_endpoints = list(config.horizon_endpoints)
    config.horizon_endpoints = urls
    setup_horizon_pools(HorizonAdminAlerter(bot, 42).notify)
    try:
        details = await StellarService().get_account_details(SOME_ACCOUNT)
    finally:
        config.horizon_endpoints = previous_endpoints
        reset_horizon_pools()

    assert details is not None
    assert details["account_id"] == SOME_ACCOUNT
    assert len(bot.messages) == 1
    assert urls[0] in bot.messages[0]["text"]
