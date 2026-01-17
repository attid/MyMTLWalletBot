import pytest
from unittest.mock import AsyncMock, MagicMock
from core.domain.entities import User, Wallet
from core.use_cases.wallet.get_balance import GetWalletBalance
from core.use_cases.user.register import RegisterUser

@pytest.mark.asyncio
async def test_get_wallet_balance_success():
    # Setup Mocks
    mock_wallet_repo = AsyncMock()
    mock_stellar_service = AsyncMock()
    
    # Mock Data
    user_id = 123
    wallet = Wallet(id=1, user_id=user_id, public_key="GKEY", is_default=True, is_free=False)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    # Mock Account Details
    mock_account = {
        "balances": [
             {"asset_type": "native", "balance": "100.0", "buying_liabilities": "0", "selling_liabilities": "0", "asset_code": None, "asset_issuer": None}
        ],
        "num_sponsoring": 0,
        "signers": ["GKEY"],
        "data": {}
    }
    mock_stellar_service.get_account_details.return_value = mock_account
    mock_stellar_service.get_selling_offers.return_value = []
    
    # Execute
    use_case = GetWalletBalance(mock_wallet_repo, mock_stellar_service)
    result = await use_case.execute(user_id)
    
    # Verify return type is List[Balance]
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].asset_code == "XLM"
    assert result[0].balance == "100.0"
    
    mock_wallet_repo.get_default_wallet.assert_called_once_with(user_id)
    mock_stellar_service.get_account_details.assert_called_once_with("GKEY")
    mock_stellar_service.get_selling_offers.assert_called_once_with("GKEY")

@pytest.mark.asyncio
async def test_get_wallet_balance_with_address():
    mock_wallet_repo = AsyncMock()
    mock_stellar_service = AsyncMock()
    
    # Mock Account Details
    mock_account = {
        "balances": [{"asset_type": "native", "balance": "50.0", "buying_liabilities": "0", "selling_liabilities": "0"}],
        "num_sponsoring": 0, "signers": ["GOTHER"], "data": {}
    }
    mock_stellar_service.get_account_details.return_value = mock_account
    mock_stellar_service.get_selling_offers.return_value = []
    
    use_case = GetWalletBalance(mock_wallet_repo, mock_stellar_service)
    result = await use_case.execute(user_id=123, public_key="GOTHER")
    
    assert len(result) == 1
    assert result[0].balance == "50.0"
    
    # Needs to ensure repo was NOT called
    mock_wallet_repo.get_default_wallet.assert_not_called()
    mock_stellar_service.get_account_details.assert_called_once_with("GOTHER")

@pytest.mark.asyncio
async def test_get_wallet_balance_no_wallet():
    mock_wallet_repo = AsyncMock()
    mock_stellar_service = AsyncMock()
    mock_wallet_repo.get_default_wallet.return_value = None
    
    use_case = GetWalletBalance(mock_wallet_repo, mock_stellar_service)
    
    with pytest.raises(ValueError, match="No default wallet found"):
        await use_case.execute(999)

@pytest.mark.asyncio
async def test_register_new_user():
    # Setup Mocks
    mock_user_repo = AsyncMock()
    mock_wallet_repo = AsyncMock()
    
    # Scenario: New User
    mock_user_repo.get_by_id.return_value = None
    mock_user_repo.create.return_value = User(id=10, username="new", language="en")
    mock_wallet_repo.create.return_value = Wallet(id=5, user_id=10, public_key="PUB", is_default=True, is_free=True)
    
    # Execute
    use_case = RegisterUser(mock_user_repo, mock_wallet_repo)
    user, wallet = await use_case.execute(10, "new", "en", "PUB", "SEC")
    
    # Verify
    mock_user_repo.create.assert_called_once()
    mock_wallet_repo.create.assert_called_once()
    assert user.id == 10
    assert wallet.public_key == "PUB"

@pytest.mark.asyncio
async def test_register_existing_user():
    # Setup Mocks
    mock_user_repo = AsyncMock()
    mock_wallet_repo = AsyncMock()
    
    # Scenario: Existing User and Wallet
    existing_user = User(id=20, username="exist", language="en")
    existing_wallet = Wallet(id=6, user_id=20, public_key="OLD_KEY", is_default=True, is_free=True)
    
    mock_user_repo.get_by_id.return_value = existing_user
    mock_wallet_repo.get_default_wallet.return_value = existing_wallet
    
    # Execute
    use_case = RegisterUser(mock_user_repo, mock_wallet_repo)
    user, wallet = await use_case.execute(20, "exist", "en", "NEW_KEY", "NEW_SEC")
    
    # Verify: Should NOT create new user or wallet
    mock_user_repo.create.assert_not_called()
    mock_wallet_repo.create.assert_not_called()
    assert user == existing_user
    assert wallet == existing_wallet
