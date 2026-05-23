from collections import defaultdict

import pytest
from stellar_sdk import Keypair

from core.domain.value_objects import Asset
from core.models.anchor_asset import AnchorAssetSupport, SepProtocol, SepProtocolSupport
from infrastructure.services.anchor_transaction_service import AnchorTransactionService


@pytest.mark.asyncio
async def test_fetch_transactions_reads_sep6_and_sep24_history():
    calls = defaultdict(int)

    async def fetch_json(method, url, params, headers, data):
        calls[(method, url)] += 1
        assert params == {"asset_code": "BTCLN"}
        assert headers is None
        assert data is None
        if url == "https://anchor.test/sep6/transactions":
            return {
                "transactions": [
                    {
                        "id": "sep6-1",
                        "kind": "deposit",
                        "status": "completed",
                        "amount_in": "10",
                        "updated_at": "2026-05-23T10:00:00Z",
                    }
                ]
            }
        if url == "https://anchor.test/sep24/transactions":
            return {
                "transactions": [
                    {
                        "id": "sep24-1",
                        "kind": "withdrawal",
                        "status": "pending_user",
                        "amount_out": "20",
                        "more_info_url": "https://anchor.test/more/sep24-1",
                    }
                ]
            }
        raise AssertionError(f"unexpected URL: {url}")

    service = AnchorTransactionService(fetch_json=fetch_json)
    support = AnchorAssetSupport(
        asset=Asset("BTCLN", "GISSUER"),
        anchor_domain="anchor.test",
        web_auth_endpoint=None,
        sep6=SepProtocolSupport(
            protocol=SepProtocol.SEP6,
            transfer_server="https://anchor.test/sep6",
        ),
        sep24=SepProtocolSupport(
            protocol=SepProtocol.SEP24,
            transfer_server="https://anchor.test/sep24",
        ),
    )

    transactions = await service.fetch_transactions(support, Keypair.random())

    assert [tx.id for tx in transactions] == ["sep6-1", "sep24-1"]
    assert transactions[0].protocol.value == "SEP-6"
    assert transactions[1].protocol.value == "SEP-24"
    assert calls[("GET", "https://anchor.test/sep6/transactions")] == 1
    assert calls[("GET", "https://anchor.test/sep24/transactions")] == 1
