import pytest
from unittest.mock import AsyncMock
from core.domain.entities import Wallet
from core.domain.value_objects import Asset
from core.use_cases.payment.send_payment import SendPayment
from infrastructure.services.stellar_service import StellarService

@pytest.mark.asyncio
async def test_send_payment_success(mock_horizon, horizon_server_config):
    # Setup Mocks
    mock_wallet_repo = AsyncMock()
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    
    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    dest_key = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    wallet = Wallet(id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    # Configure mock_horizon
    mock_horizon.set_account(public_key) # Source
    mock_horizon.set_account(dest_key) # Destination
    
    # Execute
    use_case = SendPayment(mock_wallet_repo, stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        destination_address=dest_key,
        asset=Asset(code="XLM"),
        amount=10.0
    )
    
    # Verify
    assert result.success is True
    assert result.xdr is not None
    assert "AAAA" in result.xdr
    
    mock_wallet_repo.get_default_wallet.assert_called_once_with(user_id)
    
@pytest.mark.asyncio
async def test_send_payment_negative_amount(horizon_server_config):
    mock_wallet_repo = AsyncMock()
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    use_case = SendPayment(mock_wallet_repo, stellar_service)
    dest_key = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    
    result = await use_case.execute(123, dest_key, Asset(code="XLM"), -5.0)
    assert result.success is False
    assert result.error_message == "Amount must be positive and finite (not unlimited)"

@pytest.mark.asyncio
async def test_send_payment_dest_not_found(mock_horizon, horizon_server_config):
    # Setup Mocks
    mock_wallet_repo = AsyncMock()
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    
    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    dest_key = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    wallet = Wallet(id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    # Configure mock_horizon: Source exists, but NOT Destination
    mock_horizon.set_account(public_key)
    mock_horizon.set_not_found(dest_key)
    
    # Execute
    use_case = SendPayment(mock_wallet_repo, stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        destination_address=dest_key,
        asset=Asset(code="XLM"),
        amount=10.0
    )
    
    # Verify
    assert result.success is False
    assert result.error_message == "Destination account does not exist"

@pytest.mark.asyncio
async def test_send_payment_create_account(mock_horizon, horizon_server_config):
    mock_wallet_repo = AsyncMock()
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    
    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    dest_key = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    wallet = Wallet(id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    # Source exists, Destination NOT
    mock_horizon.set_account(public_key)
    mock_horizon.set_not_found(dest_key)
    
    use_case = SendPayment(mock_wallet_repo, stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        destination_address=dest_key,
        asset=Asset(code="XLM"),
        amount=10.0,
        create_account=True
    )
    
    assert result.success is True
    assert result.xdr is not None
    assert "AAAA" in result.xdr

@pytest.mark.asyncio
async def test_create_cheque_success(mock_horizon, horizon_server_config):
    from core.use_cases.cheque.create_cheque import CreateCheque
    
    mock_wallet_repo = AsyncMock()
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    
    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    wallet = Wallet(id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    # Source exists
    mock_horizon.set_account(public_key)
    
    use_case = CreateCheque(mock_wallet_repo, stellar_service)
    result = await use_case.execute(user_id, amount=10.0, count=5, memo="UUID")
    
    assert result.success is True
    assert result.xdr is not None
    assert "AAAA" in result.xdr
