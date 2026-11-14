from collections import defaultdict
from datetime import timedelta
import asyncio

import pytest

from core.domain.value_objects import Asset
from core.models.anchor_asset import AnchorAssetSupport, SepProtocol, SepProtocolSupport
from infrastructure.services.anchor_discovery_service import AnchorDiscoveryService


ISSUER = "GDPKQ2TSNJOFSEE7XSUXPWRP27H6GFGLWD7JCHNEYYWQVGFA543EVBVT"


class FakeAnchorHttp:
    def __init__(self):
        self.calls = defaultdict(int)

    async def fetch_json(self, url: str):
        self.calls[url] += 1
        if url.endswith(f"/accounts/{ISSUER}"):
            return {"home_domain": "kbtrading.org"}
        if url == "https://kbtrading.org/sep6/info":
            return {
                "deposit": {
                    "BTCLN": {
                        "enabled": True,
                        "min_amount": 1000.0,
                        "max_amount": 500000.0,
                        "fee_percent": 1.0,
                    }
                },
                "withdraw": {
                    "BTCLN": {
                        "enabled": True,
                        "min_amount": 10000.0,
                        "max_amount": 500000.0,
                        "types": {
                            "lightning": {
                                "fields": {
                                    "dest": {"description": "Bitcoin Lightning invoice"}
                                }
                            }
                        },
                    }
                },
                "transactions": {"enabled": True, "authentication_required": True},
            }
        if url == "https://kbtrading.org/sep24/info":
            return {
                "deposit": {"BTCLN": {"enabled": True, "min_amount": 1000.0}},
                "withdraw": {"BTCLN": {"enabled": True, "min_amount": 10000.0}},
            }
        raise AssertionError(f"unexpected json URL: {url}")

    async def fetch_text(self, url: str):
        self.calls[url] += 1
        if url == "https://kbtrading.org/.well-known/stellar.toml":
            return """
                TRANSFER_SERVER="https://kbtrading.org/sep6"
                TRANSFER_SERVER_SEP0024="https://kbtrading.org/sep24"
                WEB_AUTH_ENDPOINT="https://kbtrading.org/auth"
            """
        raise AssertionError(f"unexpected text URL: {url}")


class FakeListAnchorHttp:
    def __init__(self):
        self.calls = defaultdict(int)

    async def fetch_json(self, url: str):
        self.calls[url] += 1
        if url.endswith(f"/accounts/{ISSUER}"):
            return {"home_domain": "list.example"}
        if url == "https://list.example/sep6/info":
            return {
                "deposit": {
                    "MTL": {
                        "enabled": True,
                    }
                }
            }
        raise TimeoutError(f"timeout: {url}")

    async def fetch_text(self, url: str):
        self.calls[url] += 1
        if url == "https://list.example/.well-known/stellar.toml":
            return 'TRANSFER_SERVER="https://list.example/sep6"'
        raise AssertionError(f"unexpected text URL: {url}")


@pytest.mark.asyncio
async def test_discover_asset_returns_sep6_and_sep24_capabilities():
    fake_http = FakeAnchorHttp()
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
    )

    support = await service.discover_asset(Asset("BTCLN", ISSUER))

    assert support is not None
    assert support.asset.code == "BTCLN"
    assert support.anchor_domain == "kbtrading.org"
    assert support.sep6 is not None
    assert support.sep6.deposit is not None
    assert support.sep6.withdraw is not None
    assert support.sep6.transactions_enabled is True
    assert support.sep24 is not None
    assert support.sep24.deposit is not None
    assert support.sep24.withdraw is not None


@pytest.mark.asyncio
async def test_discover_asset_uses_one_hour_cache_by_asset():
    fake_http = FakeAnchorHttp()
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
    )

    first = await service.discover_asset(Asset("BTCLN", ISSUER))
    second = await service.discover_asset(Asset("BTCLN", ISSUER))

    assert first is second
    assert fake_http.calls[f"https://horizon.test/accounts/{ISSUER}"] == 1
    assert fake_http.calls["https://kbtrading.org/.well-known/stellar.toml"] == 1
    assert fake_http.calls["https://kbtrading.org/sep6/info"] == 1
    assert fake_http.calls["https://kbtrading.org/sep24/info"] == 1


@pytest.mark.asyncio
async def test_discover_assets_filters_by_sep_info_without_repeated_fetches():
    fake_http = FakeListAnchorHttp()
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
    )

    supported = await service.discover_assets(
        [
            Asset("EURMTL", ISSUER),
            Asset("MTL", ISSUER),
            Asset("MTLRECT", ISSUER),
        ]
    )

    assert [support.asset.code for support in supported] == ["MTL"]
    assert fake_http.calls[f"https://horizon.test/accounts/{ISSUER}"] == 1
    assert fake_http.calls["https://list.example/.well-known/stellar.toml"] == 1
    assert fake_http.calls["https://list.example/sep6/info"] == 1


def make_group_support(asset: Asset) -> AnchorAssetSupport:
    return AnchorAssetSupport(
        asset=asset,
        anchor_domain=f"{asset.code.lower()}.example",
        web_auth_endpoint=None,
        sep6=SepProtocolSupport(
            protocol=SepProtocol.SEP6,
            transfer_server=f"https://{asset.code.lower()}.example/sep6",
        ),
    )


@pytest.mark.asyncio
async def test_discover_assets_skips_an_anchor_that_times_out():
    class TimeoutDiscoveryService(AnchorDiscoveryService):
        async def discover_anchor_assets(self, issuer, assets):
            if any(asset.code == "SLOW" for asset in assets):
                await asyncio.sleep(0.05)
            return [make_group_support(asset) for asset in assets]

    service = TimeoutDiscoveryService(summary_timeout=0.01)

    supported = await service.discover_assets(
        [
            Asset("FAST", "GFAST"),
            Asset("SLOW", "GSLOW"),
        ]
    )

    assert [support.asset.code for support in supported] == ["FAST"]


@pytest.mark.asyncio
async def test_discover_assets_starts_next_group_when_one_slot_frees():
    started = []

    class SlidingWindowDiscoveryService(AnchorDiscoveryService):
        async def discover_anchor_assets(self, issuer, assets):
            started.append(assets[0].code)
            if assets[0].code == "A1":
                await asyncio.sleep(0.05)
            else:
                await asyncio.sleep(0.01)
            return [make_group_support(asset) for asset in assets]

    service = SlidingWindowDiscoveryService(list_concurrency=3)

    await service.discover_assets([Asset(f"A{i}", f"GISSUER{i}") for i in range(4)])

    assert started[:3] == ["A0", "A1", "A2"]
    assert started[3] == "A3"


@pytest.mark.asyncio
async def test_discover_assets_limits_parallel_anchor_checks_to_three():
    class TrackingDiscoveryService(AnchorDiscoveryService):
        def __init__(self):
            super().__init__(list_concurrency=3)
            self.active = 0
            self.max_active = 0

        async def discover_anchor_assets(self, issuer, assets):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return [make_group_support(asset) for asset in assets]

    service = TrackingDiscoveryService()
    assets = [Asset(f"A{i}", f"GISSUER{i}") for i in range(8)]

    supported = await service.discover_assets(assets)

    assert service.max_active == 3
    assert [support.asset.code for support in supported] == [
        "A0",
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A6",
        "A7",
    ]


@pytest.mark.asyncio
async def test_discover_assets_fetches_one_chain_per_issuer():
    """Regression: same-issuer assets must not queue behind each other."""
    fake_http = FakeAnchorHttp()
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
        summary_timeout=1.0,
    )

    supported = await service.discover_assets(
        [Asset("BTCLN", ISSUER), Asset("OTHER", ISSUER)]
    )

    assert [support.asset.code for support in supported] == ["BTCLN"]
    assert fake_http.calls[f"https://horizon.test/accounts/{ISSUER}"] == 1
    assert fake_http.calls["https://kbtrading.org/sep6/info"] == 1
    assert fake_http.calls["https://kbtrading.org/sep24/info"] == 1


class CaseSensitiveAnchorHttp(FakeAnchorHttp):
    """Anchor advertises `yXLM` while the wallet holds `YXLM`."""

    async def fetch_text(self, url: str):
        self.calls[url] += 1
        if url == "https://kbtrading.org/.well-known/stellar.toml":
            return """
                TRANSFER_SERVER_SEP0024="https://kbtrading.org/sep24"
                WEB_AUTH_ENDPOINT="https://kbtrading.org/auth"
                SIGNING_KEY="GSIGNINGKEY"
            """
        raise AssertionError(f"unexpected text URL: {url}")

    async def fetch_json(self, url: str):
        self.calls[url] += 1
        if url.endswith(f"/accounts/{ISSUER}"):
            return {"home_domain": "kbtrading.org"}
        if url == "https://kbtrading.org/sep24/info":
            return {"deposit": {"yXLM": {"enabled": True}}}
        raise AssertionError(f"unexpected json URL: {url}")


@pytest.mark.asyncio
async def test_discovery_reads_signing_key_and_resolves_asset_case():
    fake_http = CaseSensitiveAnchorHttp()
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
    )

    support = await service.discover_asset(Asset("YXLM", ISSUER))

    assert support is not None
    assert support.signing_key == "GSIGNINGKEY"
    assert support.sep24 is not None
    # `/info` key spelling is echoed verbatim for protocol requests.
    assert support.asset_code_for(SepProtocol.SEP24) == "yXLM"
    assert support.sep24.asset_code == "yXLM"


@pytest.mark.asyncio
async def test_discovery_keeps_exact_case_when_it_matches():
    fake_http = FakeAnchorHttp()
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
    )

    support = await service.discover_asset(Asset("BTCLN", ISSUER))

    assert support is not None
    assert support.asset_code_for(SepProtocol.SEP24) == "BTCLN"
    assert support.signing_key is None


class FlakyAnchorHttp(FakeAnchorHttp):
    """The anchor `stellar.toml` fails a configurable number of times."""

    def __init__(self, failures: int = 1):
        super().__init__()
        self.remaining_failures = failures

    async def fetch_text(self, url: str):
        if url.endswith("stellar.toml") and self.remaining_failures > 0:
            self.remaining_failures -= 1
            self.calls[url] += 1
            raise TimeoutError("slow anchor")
        return await super().fetch_text(url)


@pytest.mark.asyncio
async def test_transient_failure_is_retried_within_the_same_call():
    fake_http = FlakyAnchorHttp(failures=1)
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
    )

    support = await service.discover_asset(Asset("BTCLN", ISSUER))

    assert support is not None
    assert fake_http.calls["https://kbtrading.org/.well-known/stellar.toml"] == 2


@pytest.mark.asyncio
async def test_failed_lookup_is_cached_for_the_negative_ttl():
    fake_http = FlakyAnchorHttp(failures=2)
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
        negative_ttl=timedelta(hours=1),
    )

    assert await service.discover_asset(Asset("BTCLN", ISSUER)) is None
    assert await service.discover_asset(Asset("BTCLN", ISSUER)) is None
    assert fake_http.calls["https://kbtrading.org/.well-known/stellar.toml"] == 2


@pytest.mark.asyncio
async def test_transient_failure_is_retried_after_negative_ttl():
    fake_http = FlakyAnchorHttp(failures=2)
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
        negative_ttl=timedelta(0),
    )

    assert await service.discover_asset(Asset("BTCLN", ISSUER)) is None
    assert await service.discover_asset(Asset("BTCLN", ISSUER)) is not None


class StatusAnchorHttp(FakeAnchorHttp):
    """First toml/info request fails with the given exception."""

    def __init__(self, exc: Exception):
        super().__init__()
        self.exc = exc
        self.remaining = 1

    async def fetch_text(self, url: str):
        if url.endswith("stellar.toml") and self.remaining:
            self.remaining -= 1
            self.calls[url] += 1
            raise self.exc
        return await super().fetch_text(url)


@pytest.mark.asyncio
async def test_permanent_failure_is_not_retried():
    from infrastructure.services.anchor_discovery_service import SepFetchError

    fake_http = StatusAnchorHttp(SepFetchError("https://x/toml", 404))
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
    )

    assert await service.discover_asset(Asset("BTCLN", ISSUER)) is None
    assert fake_http.calls["https://kbtrading.org/.well-known/stellar.toml"] == 1


@pytest.mark.asyncio
async def test_unknown_host_is_not_retried():
    fake_http = StatusAnchorHttp(
        Exception(
            "Ошибка при выполнении запроса: Cannot connect to host x:443 ssl:default [Name or service not known]"
        )
    )
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
    )

    assert await service.discover_asset(Asset("BTCLN", ISSUER)) is None
    assert fake_http.calls["https://kbtrading.org/.well-known/stellar.toml"] == 1


@pytest.mark.asyncio
async def test_server_error_is_retried():
    from infrastructure.services.anchor_discovery_service import SepFetchError

    fake_http = StatusAnchorHttp(SepFetchError("https://x/toml", 503))
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
    )

    support = await service.discover_asset(Asset("BTCLN", ISSUER))

    assert support is not None
    assert fake_http.calls["https://kbtrading.org/.well-known/stellar.toml"] == 2


@pytest.mark.asyncio
async def test_permanent_failure_is_cached_for_the_full_ttl():
    from infrastructure.services.anchor_discovery_service import SepFetchError

    fake_http = StatusAnchorHttp(SepFetchError("https://x/toml", 404))
    service = AnchorDiscoveryService(
        fetch_json=fake_http.fetch_json,
        fetch_text=fake_http.fetch_text,
        horizon_url="https://horizon.test",
        negative_ttl=timedelta(0),
    )

    assert await service.discover_asset(Asset("BTCLN", ISSUER)) is None
    assert await service.discover_asset(Asset("BTCLN", ISSUER)) is None
    assert fake_http.calls["https://kbtrading.org/.well-known/stellar.toml"] == 1


@pytest.mark.asyncio
async def test_total_budget_marks_the_result_as_truncated():
    class SlowDiscoveryService(AnchorDiscoveryService):
        async def discover_anchor_assets(self, issuer, assets):
            await asyncio.sleep(0.2)
            return [make_group_support(asset) for asset in assets]

    service = SlowDiscoveryService(total_timeout=0.01, summary_timeout=5.0)

    supported = await service.discover_assets([Asset("A0", "GISSUER0")])

    assert supported == []
    assert service.last_call_truncated is True


@pytest.mark.asyncio
async def test_total_budget_flag_is_reset_on_the_next_call():
    class SlowDiscoveryService(AnchorDiscoveryService):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.slow = True

        async def discover_anchor_assets(self, issuer, assets):
            if self.slow:
                await asyncio.sleep(0.2)
            return [make_group_support(asset) for asset in assets]

    service = SlowDiscoveryService(total_timeout=0.01, summary_timeout=5.0)
    assert await service.discover_assets([Asset("A0", "GISSUER0")]) == []
    assert service.last_call_truncated is True

    service.slow = False
    supported = await service.discover_assets([Asset("A0", "GISSUER0")])

    assert [support.asset.code for support in supported] == ["A0"]
    assert service.last_call_truncated is False


@pytest.mark.asyncio
async def test_progress_reports_completed_assets_per_anchor():
    class GroupDiscoveryService(AnchorDiscoveryService):
        async def discover_anchor_assets(self, issuer, assets):
            await asyncio.sleep(0)
            return [make_group_support(asset) for asset in assets]

    service = GroupDiscoveryService(list_concurrency=3)
    ticks = []

    await service.discover_assets(
        [
            Asset("A0", "GISSUER0"),
            Asset("A1", "GISSUER0"),
            Asset("B0", "GISSUER1"),
        ],
        on_progress=lambda done, total: ticks.append((done, total)),
    )

    assert ticks[0] == (0, 3)
    assert ticks[-1] == (3, 3)
    assert all(total == 3 for _, total in ticks)
