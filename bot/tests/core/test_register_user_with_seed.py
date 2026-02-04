import pytest
from unittest.mock import AsyncMock
from core.domain.entities import User, Wallet
from core.use_cases.user.register import RegisterUser

@pytest.mark.asyncio
async def test_register_new_user_with_seed():
    # Setup Mocks
    mock_user_repo = AsyncMock()
    mock_wallet_repo = AsyncMock()
    
    # Scenario: New User with seed
    user_id = 11
    username = "seed_user"
    language = "en"
    pub_key = "PUB_KEY"
    sec_key = "SEC_KEY"
    seed_key = "SEED_PHRASE"

    mock_user_repo.get_by_id.return_value = None
    # We mock the return value of create methods to return what they were passed roughly, or just dummy objects
    mock_user_repo.create.return_value = User(id=user_id, username=username, language=language)
    
    # Need to verify that wallet_repo.create is called with a Wallet object containing seed_key
    async def create_wallet_side_effect(wallet: Wallet):
        return wallet
    mock_wallet_repo.create.side_effect = create_wallet_side_effect
    
    # Execute
    use_case = RegisterUser(mock_user_repo, mock_wallet_repo)
    user, wallet = await use_case.execute(user_id, username, language, pub_key, sec_key, seed_key)
    
    # Verify
    mock_user_repo.create.assert_called_once()
    mock_wallet_repo.create.assert_called_once()
    
    # Check arguments passed to wallet creation
    created_wallet = mock_wallet_repo.create.call_args[0][0]
    assert isinstance(created_wallet, Wallet)
    assert created_wallet.user_id == user_id
    assert created_wallet.public_key == pub_key
    assert created_wallet.secret_key == sec_key
    assert created_wallet.seed_key == seed_key
    assert created_wallet.is_default is True

@pytest.mark.asyncio
async def test_register_existing_user_missing_wallet_recreated_with_seed():
    # Setup Mocks
    mock_user_repo = AsyncMock()
    mock_wallet_repo = AsyncMock()
    
    user_id = 12
    username = "exist_user"
    
    mock_user_repo.get_by_id.return_value = User(id=user_id, username=username, language="en")
    mock_wallet_repo.get_default_wallet.return_value = None # No wallet found
    
    async def create_wallet_side_effect(wallet: Wallet):
        return wallet
    mock_wallet_repo.create.side_effect = create_wallet_side_effect

    # Execute
    use_case = RegisterUser(mock_user_repo, mock_wallet_repo)
    user, wallet = await use_case.execute(user_id, username, "en", "PUB", "SEC", "SEED")
    
    # Verify
    mock_wallet_repo.create.assert_called_once()
    created_wallet = mock_wallet_repo.create.call_args[0][0]
    assert created_wallet.seed_key == "SEED"
