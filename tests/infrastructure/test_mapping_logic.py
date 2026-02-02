import pytest

@pytest.mark.asyncio
async def test_map_notification_created_offer_id(notification_service):
    """
    Test that _map_payload_to_operation correctly prefers created_offer_id
    when offer_id is 0 or missing.
    """
    payload = {
        "operation": {
            "id": "123",
            "type": "manage_sell_offer",
            "account": "GABC",
            "amount": "100",
            "price": "1.0",
            "offer_id": "0",  # Simulate new offer
            "created_offer_id": "99999", # Real ID
            "asset": {"asset_type": "native"}
        }
    }
    
    op = notification_service._map_payload_to_operation(payload)
    assert op is not None
    assert op.operation == "manage_sell_offer"
    assert op.offer_id == 99999, f"Expected offer_id 99999, got {op.offer_id}"
