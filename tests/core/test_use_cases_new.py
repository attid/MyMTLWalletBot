
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.use_cases.wallet.add_wallet import AddWallet
from core.use_cases.user.update_profile import UpdateUserProfile
from core.use_cases.user.manage_user import DeleteUser, AddDonation
from core.domain.entities import Wallet, User

@pytest.fixture
def mock_wallet_repo():
    repo = MagicMock()
    repo.count_free_wallets = AsyncMock()
    repo.create = AsyncMock()
    repo.set_default_wallet = AsyncMock()
    repo.delete_all_by_user = AsyncMock()
    return repo

@pytest.fixture
def mock_user_repo():
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock()
    repo.update_donate_sum = AsyncMock()
    return repo

@pytest.mark.asyncio
async def test_add_wallet_success(mock_wallet_repo):
    use_case = AddWallet(mock_wallet_repo)
    mock_wallet_repo.count_free_wallets.return_value = 0
    mock_wallet_repo.create.return_value = Wallet(id=1, user_id=123, public_key="PUB", is_default=True, is_free=True)
    
    result = await use_case.execute(user_id=123, public_key="PUB", secret_key="SEC", is_free=True, is_default=True)
    
    mock_wallet_repo.count_free_wallets.assert_called_once_with(123)
    mock_wallet_repo.create.assert_called_once()
    mock_wallet_repo.set_default_wallet.assert_called_once_with(123, "PUB")
    assert result.id == 1

@pytest.mark.asyncio
async def test_add_wallet_limit_reached(mock_wallet_repo):
    use_case = AddWallet(mock_wallet_repo)
    mock_wallet_repo.count_free_wallets.return_value = 3 # Max limit is >2 (so 0,1,2 ok, 3 fails)
    
    with pytest.raises(ValueError, match="Maximum number of free wallets reached"):
        await use_case.execute(user_id=123, public_key="PUB", secret_key="SEC", is_free=True)

@pytest.mark.asyncio
async def test_add_wallet_read_only(mock_wallet_repo):
    use_case = AddWallet(mock_wallet_repo)
    mock_wallet_repo.create.return_value = Wallet(id=1, user_id=123, public_key="PUB", is_default=False, is_free=False, use_pin=10)
    
    # is_read_only=True
    await use_case.execute(user_id=123, public_key="PUB", secret_key=None, is_read_only=True)
    
    args, _ = mock_wallet_repo.create.call_args
    wallet = args[0]
    assert wallet.use_pin == 10
    assert wallet.secret_key is None

@pytest.mark.asyncio
async def test_update_user_profile(mock_user_repo):
    use_case = UpdateUserProfile(mock_user_repo)
    existing_user = User(id=123, username="old", language="en", default_address="addr", can_5000=0)
    mock_user_repo.get_by_id.return_value = existing_user
    mock_user_repo.update.return_value = existing_user # Returns updated user ideally
    
    updated_user = await use_case.execute(user_id=123, username="new")
    
    assert existing_user.username == "new" # Modified in place
    mock_user_repo.update.assert_called_once()

@pytest.mark.asyncio
async def test_update_user_profile_no_change(mock_user_repo):
    use_case = UpdateUserProfile(mock_user_repo)
    existing_user = User(id=123, username="old", language="en")
    mock_user_repo.get_by_id.return_value = existing_user
    
    await use_case.execute(user_id=123, username="old")
    
    mock_user_repo.update.assert_not_called()

@pytest.mark.asyncio
async def test_delete_user(mock_user_repo, mock_wallet_repo):
    use_case = DeleteUser(mock_user_repo, mock_wallet_repo)
    
    await use_case.execute(user_id=123)
    
    mock_wallet_repo.delete_all_by_user.assert_called_once_with(123)
    mock_user_repo.delete.assert_called_once_with(123)

@pytest.mark.asyncio
async def test_add_donation(mock_user_repo):
    use_case = AddDonation(mock_user_repo)
    
    await use_case.execute(user_id=123, amount=10.0)
    
    mock_user_repo.update_donate_sum.assert_called_once_with(123, 10.0)
