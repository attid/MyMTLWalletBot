
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from routers.start_msg import get_start_text
from core.domain.value_objects import Balance
from core.use_cases.wallet.get_balance import GetWalletBalance

@pytest.mark.asyncio
async def test_get_start_text_show_less(mock_session, mock_app_context):
    # Setup
    user_id = 123
    mock_state = MagicMock()
    # show_more = False (default)
    mock_state.get_data = AsyncMock(return_value={'show_more': False})
    mock_state.update_data = AsyncMock()
    
    mock_app_context.localization_service.get_text.return_value = 'Your Balance'
    
    # Mock Wallet Repository
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GUSER"
    mock_wallet.is_free = False
    mock_wallet.assets_visibility = None # Visible by default
    
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_wallet_repo.get_info = AsyncMock(return_value="User Info")
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    # Mock Secret Service
    mock_secret_service = AsyncMock()
    mock_secret_service.is_ton_wallet = AsyncMock(return_value=False)
    mock_app_context.use_case_factory.create_wallet_secret_service.return_value = mock_secret_service
    
    # Mock Balance Use Case
    mock_balance_uc = AsyncMock()
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(balance="100.0", asset_code="EURMTL", asset_issuer="GI", asset_type="credit_alphanum12"),
        Balance(balance="50.0", asset_code="XLM", asset_issuer="native", asset_type="native"),
        Balance(balance="10.0", asset_code="BTC", asset_issuer="GI", asset_type="credit_alphanum12"),
    ])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc
    
    with patch("routers.start_msg.my_gettext", return_value="Balance"):
        # Execute
        text = await get_start_text(mock_session, mock_state, user_id, app_context=mock_app_context)
    
    # Assertions
    assert "EURMTL" in text
    assert "BTC" not in text
    # XLM might be not present because it's not EURMTL and wallet is not free.
    assert "XLM" not in text

@pytest.mark.asyncio
async def test_get_start_text_show_more(mock_session, mock_app_context):
    # Setup
    user_id = 123
    mock_state = MagicMock()
    # show_more = True
    mock_state.get_data = AsyncMock(return_value={'show_more': True})
    mock_state.update_data = AsyncMock()
    
    # Mock Wallet Repository
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GUSER"
    mock_wallet.is_free = False
    mock_wallet.assets_visibility = None
    
    mock_wallet_repo = MagicMock()
    mock_wallet_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
    mock_wallet_repo.get_info = AsyncMock(return_value="User Info")
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    
    # Mock Secret Service
    mock_secret_service = AsyncMock()
    mock_secret_service.is_ton_wallet = AsyncMock(return_value=False)
    mock_app_context.use_case_factory.create_wallet_secret_service.return_value = mock_secret_service
    
    # Mock Balance Use Case
    mock_balance_uc = AsyncMock()
    mock_balance_uc.execute = AsyncMock(return_value=[
        Balance(balance="100.0", asset_code="EURMTL", asset_issuer="GI", asset_type="credit_alphanum12"),
        Balance(balance="50.0", asset_code="XLM", asset_issuer="native", asset_type="native"),
        Balance(balance="10.0", asset_code="BTC", asset_issuer="GI", asset_type="credit_alphanum12"),
    ])
    mock_app_context.use_case_factory.create_get_wallet_balance.return_value = mock_balance_uc
    
    with patch("routers.start_msg.my_gettext", return_value="Balance"):
        text = await get_start_text(mock_session, mock_state, user_id, app_context=mock_app_context)
    
    assert "EURMTL" in text
    assert "BTC" in text
    assert "XLM" in text
