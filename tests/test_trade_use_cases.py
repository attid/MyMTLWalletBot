import pytest
from unittest.mock import AsyncMock
from core.domain.entities import Wallet
from core.domain.value_objects import Asset
from core.use_cases.trade.swap_assets import SwapAssets
from core.use_cases.trade.manage_offer import ManageOffer

@pytest.mark.asyncio
async def test_swap_assets_success():
    mock_wallet_repo = AsyncMock()
    mock_stellar_service = AsyncMock()
    
    user_id = 123
    wallet = Wallet(id=1, user_id=user_id, public_key="GSOURCE", is_default=True, is_free=True)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    mock_stellar_service.swap_assets.return_value = "AAAA...SWAPXDR"
    
    use_case = SwapAssets(mock_wallet_repo, mock_stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        send_asset=Asset(code="XLM"),
        send_amount=10.0,
        receive_asset=Asset(code="EURMTL"),
        receive_amount=20.0,
        strict_receive=False
    )
    
    assert result.success is True
    assert result.xdr == "AAAA...SWAPXDR"
    
    mock_stellar_service.swap_assets.assert_called_once()
    args, kwargs = mock_stellar_service.swap_assets.call_args
    assert kwargs['strict_receive'] is False

@pytest.mark.asyncio
async def test_manage_offer_success():
    mock_wallet_repo = AsyncMock()
    mock_stellar_service = AsyncMock()
    
    user_id = 123
    wallet = Wallet(id=1, user_id=user_id, public_key="GSOURCE", is_default=True, is_free=True)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    mock_stellar_service.manage_offer.return_value = "AAAA...OFFERXDR"
    
    use_case = ManageOffer(mock_wallet_repo, mock_stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        selling=Asset(code="XLM"),
        buying=Asset(code="EURMTL"),
        amount=10.0,
        price=2.0
    )
    
    assert result.success is True
    assert result.xdr == "AAAA...OFFERXDR"
    
    mock_stellar_service.manage_offer.assert_called_once()
    args, kwargs = mock_stellar_service.manage_offer.call_args
    assert kwargs['amount'] == '10.0'
    assert kwargs['price'] == '2.0'
