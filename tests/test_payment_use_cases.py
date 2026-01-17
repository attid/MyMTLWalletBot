import pytest
from unittest.mock import AsyncMock
from core.domain.entities import Wallet
from core.domain.value_objects import Asset
from core.use_cases.payment.send_payment import SendPayment

@pytest.mark.asyncio
async def test_send_payment_success():
    # Setup Mocks
    mock_wallet_repo = AsyncMock()
    mock_stellar_service = AsyncMock()
    
    user_id = 123
    wallet = Wallet(id=1, user_id=user_id, public_key="GSOURCE", is_default=True, is_free=True)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    mock_stellar_service.check_account_exists.return_value = True
    mock_stellar_service.build_payment_transaction.return_value = "AAAA...XDR"
    
    # Execute
    use_case = SendPayment(mock_wallet_repo, mock_stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        destination_address="GDEST",
        asset=Asset(code="XLM"),
        amount=10.0
    )
    
    # Verify
    assert result.success is True
    assert result.xdr == "AAAA...XDR"
    
    mock_wallet_repo.get_default_wallet.assert_called_once_with(user_id)
    mock_stellar_service.check_account_exists.assert_called_once_with("GDEST")
    mock_stellar_service.build_payment_transaction.assert_called_once()
    
@pytest.mark.asyncio
async def test_send_payment_negative_amount():
    mock_wallet_repo = AsyncMock()
    mock_stellar_service = AsyncMock()
    use_case = SendPayment(mock_wallet_repo, mock_stellar_service)
    
    result = await use_case.execute(123, "GDEST", Asset(code="XLM"), -5.0)
    assert result.success is False
    assert result.error_message == "Amount must be positive"

@pytest.mark.asyncio
async def test_send_payment_dest_not_found():
    # Setup Mocks
    mock_wallet_repo = AsyncMock()
    mock_stellar_service = AsyncMock()
    
    user_id = 123
    wallet = Wallet(id=1, user_id=user_id, public_key="GSOURCE", is_default=True, is_free=True)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    mock_stellar_service.check_account_exists.return_value = False
    
    # Execute
    use_case = SendPayment(mock_wallet_repo, mock_stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        destination_address="GDEST",
        asset=Asset(code="XLM"),
        amount=10.0
    )
    
    # Verify
    assert result.success is False
    assert result.error_message == "Destination account does not exist"

@pytest.mark.asyncio
async def test_create_cheque_success():
    from core.use_cases.cheque.create_cheque import CreateCheque
    
    mock_wallet_repo = AsyncMock()
    mock_stellar_service = AsyncMock()
    
    user_id = 123
    wallet = Wallet(id=1, user_id=user_id, public_key="GSOURCE", is_default=True, is_free=True)
    mock_wallet_repo.get_default_wallet.return_value = wallet
    
    mock_stellar_service.build_payment_transaction.return_value = "AAAA...CHEQUEXDR"
    
    use_case = CreateCheque(mock_wallet_repo, mock_stellar_service)
    result = await use_case.execute(user_id, amount=10.0, count=5, memo="UUID")
    
    assert result.success is True
    assert result.xdr == "AAAA...CHEQUEXDR"
    
    # check amount = 10 * 5 = 50.0
    # check memo = UUID
    # check destination = CHEQUE_PUBLIC_KEY (we assume Use Case uses constant)
    mock_stellar_service.build_payment_transaction.assert_called_once()
    args, kwargs = mock_stellar_service.build_payment_transaction.call_args
    assert kwargs['amount'] == '50.0'
    assert kwargs['memo'] == 'UUID'
