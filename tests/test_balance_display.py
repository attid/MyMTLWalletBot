
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from routers.start_msg import get_start_text
from core.domain.value_objects import Balance
from core.use_cases.wallet.get_balance import GetWalletBalance

@pytest.mark.asyncio
async def test_get_start_text_show_less(mock_session):
    # Setup
    user_id = 123
    mock_state = MagicMock()
    # show_more = False (default)
    mock_state.get_data = AsyncMock(return_value={'show_more': False})
    mock_state.update_data = AsyncMock()
    
    app_context = MagicMock()
    app_context.localization_service.get_text.return_value = 'Your Balance'
    
    # Mock Repository
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GUSER"
    mock_wallet.is_free = False
    mock_wallet.assets_visibility = None # Visible by default
    
    # We need to patch the classes where they are defined, since they are imported locally
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository") as MockRepoClass, \
         patch("infrastructure.services.stellar_service.StellarService") as MockServiceClass, \
         patch("core.use_cases.wallet.get_balance.GetWalletBalance") as MockUseCaseClass, \
         patch("infrastructure.services.wallet_secret_service.SqlAlchemyWalletSecretService") as MockSecretServiceClass, \
         patch("routers.start_msg.my_gettext", return_value="Balance"):
         
        # Mock Secret Service
        mock_secret_service = MockSecretServiceClass.return_value
        mock_secret_service.is_ton_wallet = AsyncMock(return_value=False)
        
        # Mock Repo
        mock_repo = MockRepoClass.return_value
        mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
        mock_repo.get_info = AsyncMock(return_value="User Info")
        
        # Mock Use Case
        mock_use_case = MockUseCaseClass.return_value
        # Return multiple assets
        mock_use_case.execute = AsyncMock(return_value=[
            Balance(balance="100.0", asset_code="EURMTL", asset_issuer="GI", asset_type="credit_alphanum12"),
            Balance(balance="50.0", asset_code="XLM", asset_issuer="native", asset_type="native"),
            Balance(balance="10.0", asset_code="BTC", asset_issuer="GI", asset_type="credit_alphanum12"),
        ])
        
        # We also need to patch config because it is used
        with patch("other.config_reader.config") as mock_config:
             mock_config.horizon_url = "https://horizon-testnet.stellar.org"
             
             # Execute
             text = await get_start_text(mock_session, mock_state, user_id, app_context)
        
        # Assertions
        assert "EURMTL" in text
        assert "BTC" not in text
        # XLM might be not present because it's not EURMTL and wallet is not free.
        assert "XLM" not in text

@pytest.mark.asyncio
async def test_get_start_text_show_more(mock_session):
    # Setup
    user_id = 123
    mock_state = MagicMock()
    # show_more = True
    mock_state.get_data = AsyncMock(return_value={'show_more': True})
    mock_state.update_data = AsyncMock()
    
    app_context = MagicMock()
    
    # Mock Repository
    mock_wallet = MagicMock()
    mock_wallet.public_key = "GUSER"
    mock_wallet.is_free = False
    mock_wallet.assets_visibility = None
    
    # We need to patch the classes where they are defined, since they are imported locally
    with patch("infrastructure.persistence.sqlalchemy_wallet_repository.SqlAlchemyWalletRepository") as MockRepoClass, \
         patch("infrastructure.services.stellar_service.StellarService") as MockServiceClass, \
         patch("core.use_cases.wallet.get_balance.GetWalletBalance") as MockUseCaseClass, \
         patch("infrastructure.services.wallet_secret_service.SqlAlchemyWalletSecretService") as MockSecretServiceClass, \
         patch("routers.start_msg.my_gettext", return_value="Balance"):
         
        mock_secret_service = MockSecretServiceClass.return_value
        mock_secret_service.is_ton_wallet = AsyncMock(return_value=False)
        
        mock_repo = MockRepoClass.return_value
        mock_repo.get_default_wallet = AsyncMock(return_value=mock_wallet)
        mock_repo.get_info = AsyncMock(return_value="User Info")
        
        mock_use_case = MockUseCaseClass.return_value
        mock_use_case.execute = AsyncMock(return_value=[
            Balance(balance="100.0", asset_code="EURMTL", asset_issuer="GI", asset_type="credit_alphanum12"),
            Balance(balance="50.0", asset_code="XLM", asset_issuer="native", asset_type="native"),
            Balance(balance="10.0", asset_code="BTC", asset_issuer="GI", asset_type="credit_alphanum12"),
        ])
        
        # We also need to patch config because it is used
        with patch("other.config_reader.config") as mock_config:
             mock_config.horizon_url = "https://horizon-testnet.stellar.org"
        
             text = await get_start_text(mock_session, mock_state, user_id, app_context)
        
        assert "EURMTL" in text
        assert "BTC" in text
        assert "XLM" in text
