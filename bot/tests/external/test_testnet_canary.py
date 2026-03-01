import os
import asyncio
from decimal import Decimal

import aiohttp
import pytest
from stellar_sdk import Account, Asset, Keypair, Network, TransactionBuilder


pytestmark = [pytest.mark.external, pytest.mark.testnet]


async def _fund_with_friendbot(
    session: aiohttp.ClientSession, friendbot_url: str, account_id: str
) -> None:
    async with session.get(
        f"{friendbot_url.rstrip('/')}?addr={account_id}", timeout=30
    ) as response:
        body = await response.text()
        assert response.status == 200, (
            f"Friendbot failed to fund account: status={response.status}, body={body}"
        )


async def _get_account(
    session: aiohttp.ClientSession, horizon_url: str, account_id: str
) -> dict:
    account_url = f"{horizon_url.rstrip('/')}/accounts/{account_id}"
    async with session.get(account_url, timeout=15) as response:
        body = await response.text()
        assert response.status == 200, (
            "Failed to fetch account from testnet horizon: "
            f"status={response.status}, body={body}"
        )
        return await response.json()


def _native_balance(account_data: dict) -> Decimal:
    for balance in account_data.get("balances", []):
        if balance.get("asset_type") == "native":
            return Decimal(balance["balance"])
    raise AssertionError("Native XLM balance not found in account data")


async def _submit_native_payment(
    session: aiohttp.ClientSession,
    horizon_url: str,
    source_keypair: Keypair,
    destination_account_id: str,
    amount: str,
) -> None:
    source_data = await _get_account(session, horizon_url, source_keypair.public_key)
    source_account = Account(
        account=source_keypair.public_key,
        sequence=int(source_data["sequence"]),
    )

    transaction = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=Network.TESTNET_NETWORK_PASSPHRASE,
            base_fee=100,
        )
        .append_payment_op(
            destination=destination_account_id,
            amount=amount,
            asset=Asset.native(),
        )
        .set_timeout(30)
        .build()
    )
    transaction.sign(source_keypair)

    async with session.post(
        f"{horizon_url.rstrip('/')}/transactions",
        data={"tx": transaction.to_xdr()},
        timeout=30,
    ) as response:
        body = await response.text()
        assert response.status == 200, (
            "Failed to submit payment transaction: "
            f"status={response.status}, body={body}"
        )


async def _wait_for_native_balance_increase(
    session: aiohttp.ClientSession,
    horizon_url: str,
    account_id: str,
    minimum_balance: Decimal,
    timeout_seconds: int = 40,
) -> dict:
    for _ in range(timeout_seconds):
        account_data = await _get_account(session, horizon_url, account_id)
        if _native_balance(account_data) >= minimum_balance:
            return account_data
        await asyncio.sleep(1)
    raise AssertionError(
        f"Timed out waiting for native balance >= {minimum_balance} on {account_id}"
    )


@pytest.mark.asyncio
async def test_friendbot_bootstrap_account_is_reachable() -> None:
    horizon_url = os.getenv(
        "HORIZON_TESTNET_URL", "https://horizon-testnet.stellar.org"
    )
    friendbot_url = os.getenv("FRIENDBOT_URL", "https://friendbot.stellar.org")
    sender = Keypair.random()
    receiver = Keypair.random()
    transfer_amount = Decimal("1.0000000")

    async with aiohttp.ClientSession() as session:
        await _fund_with_friendbot(session, friendbot_url, sender.public_key)
        await _fund_with_friendbot(session, friendbot_url, receiver.public_key)

        sender_data = await _get_account(session, horizon_url, sender.public_key)
        receiver_data_before = await _get_account(
            session, horizon_url, receiver.public_key
        )

        # Baseline shape checks prove accounts are active and parseable.
        assert sender_data.get("account_id") == sender.public_key
        assert receiver_data_before.get("account_id") == receiver.public_key
        assert "sequence" in sender_data
        assert isinstance(sender_data.get("balances"), list)

        receiver_balance_before = _native_balance(receiver_data_before)

        await _submit_native_payment(
            session=session,
            horizon_url=horizon_url,
            source_keypair=sender,
            destination_account_id=receiver.public_key,
            amount=str(transfer_amount),
        )

        receiver_data_after = await _wait_for_native_balance_increase(
            session=session,
            horizon_url=horizon_url,
            account_id=receiver.public_key,
            minimum_balance=receiver_balance_before + transfer_amount,
        )

    assert (
        _native_balance(receiver_data_after)
        >= receiver_balance_before + transfer_amount
    )
