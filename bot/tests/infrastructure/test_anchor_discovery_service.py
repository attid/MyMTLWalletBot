from collections import defaultdict

import pytest

from core.domain.value_objects import Asset
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
