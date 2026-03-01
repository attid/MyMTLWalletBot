import os

import aiohttp
import pytest


pytestmark = [pytest.mark.external, pytest.mark.testnet]


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise AssertionError(f"Missing required env var: {name}")
    return value


@pytest.mark.asyncio
async def test_testnet_master_account_is_reachable() -> None:
    horizon_url = os.getenv(
        "HORIZON_TESTNET_URL", "https://horizon-testnet.stellar.org"
    )
    master_public_key = require_env("TESTNET_MASTER_PUBLIC_KEY")
    require_env("TESTNET_MASTER_SECRET_KEY")

    account_url = f"{horizon_url.rstrip('/')}/accounts/{master_public_key}"

    async with aiohttp.ClientSession() as session:
        async with session.get(account_url, timeout=15) as response:
            body = await response.text()
            assert response.status == 200, (
                "Failed to fetch testnet master account: "
                f"status={response.status}, body={body}"
            )
            data = await response.json()

    # Minimal shape checks prove account is active and parseable.
    assert data.get("account_id") == master_public_key
    assert "sequence" in data
    assert isinstance(data.get("balances"), list)
