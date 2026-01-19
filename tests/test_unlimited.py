
import pytest
from unittest.mock import MagicMock, AsyncMock
from core.use_cases.payment.send_payment import SendPayment
from core.use_cases.trade.swap_assets import SwapAssets
from core.domain.value_objects import Asset

@pytest.mark.asyncio
async def test_send_payment_unlimited_amount():
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=MagicMock(public_key="GSOURCE"))
    
    mock_service = MagicMock()
    mock_service.check_account_exists = AsyncMock(return_value=True)
    
    use_case = SendPayment(mock_repo, mock_service)
    
    # Passing unlimited amount
    result = await use_case.execute(
        user_id=123,
        destination_address="GADDR",
        asset=Asset(code="XLM", issuer=None),
        amount=float('inf')
    )
    
    # We expect it to FAIL or return FALSE.
    assert result.success is False
    assert "unlimited" in result.error_message.lower() or "finite" in result.error_message.lower()

@pytest.mark.asyncio
async def test_swap_assets_unlimited_amount():
    mock_repo = MagicMock()
    mock_repo.get_default_wallet = AsyncMock(return_value=MagicMock(public_key="GSOURCE"))
    
    mock_service = MagicMock()
    
    use_case = SwapAssets(mock_repo, mock_service)
    
    result = await use_case.execute(
        user_id=123,
        send_asset=Asset(code="XLM", issuer=None),
        send_amount=float('inf'),
        receive_asset=Asset(code="USDC", issuer="GISA"),
        receive_amount=10.0
    )
    
    assert result.success is False
    assert "unlimited" in result.error_message.lower() or "finite" in result.error_message.lower()
