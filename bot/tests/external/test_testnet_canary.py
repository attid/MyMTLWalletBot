import os

import aiohttp
import pytest
from stellar_sdk import Keypair


pytestmark = [pytest.mark.external, pytest.mark.testnet]


@pytest.mark.asyncio
async def test_friendbot_bootstrap_account_is_reachable() -> None:
    horizon_url = os.getenv(
        "HORIZON_TESTNET_URL", "https://horizon-testnet.stellar.org"
    )
    friendbot_url = os.getenv("FRIENDBOT_URL", "https://friendbot.stellar.org")
    account = Keypair.random()
    account_id = account.public_key

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{friendbot_url.rstrip('/')}?addr={account_id}", timeout=30
        ) as response:
            body = await response.text()
            assert response.status == 200, (
                "Friendbot failed to fund account: "
                f"status={response.status}, body={body}"
            )

    account_url = f"{horizon_url.rstrip('/')}/accounts/{account_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(account_url, timeout=15) as response:
            body = await response.text()
            assert response.status == 200, (
                "Failed to fetch testnet master account: "
                f"status={response.status}, body={body}"
            )
            data = await response.json()

    # Minimal shape checks prove account is active and parseable.
    assert data.get("account_id") == account_id
    assert "sequence" in data
    assert isinstance(data.get("balances"), list)
