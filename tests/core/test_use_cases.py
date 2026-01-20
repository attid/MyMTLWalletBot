import pytest
from unittest.mock import AsyncMock
from core.interfaces.repositories import IUserRepository, IWalletRepository
from core.domain.entities import User, Wallet
from core.use_cases.wallet.get_balance import GetWalletBalance
from core.use_cases.user.register import RegisterUser
from infrastructure.services.stellar_service import StellarService

@pytest.mark.asyncio
async def test_get_wallet_balance_success(mock_horizon, horizon_server_config):
    # Setup Mocks
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    
    # Mock Data
    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    wallet = Wallet(id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=False)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    # Configure mock_horizon instead of mocking service
    mock_horizon.set_account(public_key, balances=[
        {"asset_type": "native", "balance": "100.0000000"}
    ])
    mock_horizon.set_offers(public_key, [])
    
    # Execute
    use_case = GetWalletBalance(mock_wallet_repo, stellar_service)
    result = await use_case.execute(user_id)
    
    # Verify return type is List[Balance]
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].asset_code == "XLM"
    assert result[0].balance == "100.0000000"
    
    mock_wallet_repo.get_default_wallet.assert_called_once_with(user_id)

@pytest.mark.asyncio
async def test_get_wallet_balance_with_address(mock_horizon, horizon_server_config):
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    public_key = "GOTHER1234567890"
    
    # Configure mock_horizon
    mock_horizon.set_account(public_key, balances=[
        {"asset_type": "native", "balance": "50.0000000"}
    ])
    mock_horizon.set_offers(public_key, [])
    
    use_case = GetWalletBalance(mock_wallet_repo, stellar_service)
    result = await use_case.execute(user_id=123, public_key=public_key)
    
    assert len(result) == 1
    assert result[0].balance == "50.0000000"
    
    # Needs to ensure repo was NOT called
    mock_wallet_repo.get_default_wallet.assert_not_called()

@pytest.mark.asyncio
async def test_get_wallet_balance_no_wallet(horizon_server_config):
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    mock_wallet_repo.get_default_wallet.return_value = None
    
    use_case = GetWalletBalance(mock_wallet_repo, stellar_service)
    
    with pytest.raises(ValueError, match="No default wallet found"):
        await use_case.execute(999)

@pytest.mark.asyncio
async def test_register_new_user():
    # Setup Mocks
    mock_user_repo = AsyncMock(spec=IUserRepository)
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    
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
    mock_user_repo = AsyncMock(spec=IUserRepository)
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    
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
