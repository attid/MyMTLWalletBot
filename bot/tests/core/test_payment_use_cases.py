import pytest
from unittest.mock import AsyncMock
from core.interfaces.repositories import IWalletRepository
from core.interfaces.services import IStellarService
from core.domain.entities import Wallet
from core.domain.value_objects import Asset
from core.use_cases.payment.send_payment import SendPayment
from infrastructure.services.stellar_service import StellarService


@pytest.mark.asyncio
async def test_send_payment_success(mock_horizon, horizon_server_config):
    # Setup Mocks
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])

    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    dest_key = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    wallet = Wallet(
        id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True
    )
    mock_wallet_repo.get_default_wallet.return_value = wallet

    # Configure mock_horizon
    mock_horizon.set_account(public_key)  # Source
    mock_horizon.set_account(dest_key)  # Destination

    # Execute
    use_case = SendPayment(mock_wallet_repo, stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        destination_address=dest_key,
        asset=Asset(code="XLM"),
        amount=10.0,
    )

    # Verify
    assert result.success is True
    assert result.xdr is not None
    assert "AAAA" in result.xdr

    mock_wallet_repo.get_default_wallet.assert_called_once_with(user_id)


@pytest.mark.asyncio
async def test_send_payment_negative_amount(horizon_server_config):
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    use_case = SendPayment(mock_wallet_repo, stellar_service)
    dest_key = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"

    result = await use_case.execute(123, dest_key, Asset(code="XLM"), -5.0)
    assert result.success is False
    assert result.error_message == "Amount must be positive and finite (not unlimited)"


@pytest.mark.asyncio
async def test_send_payment_dest_not_found(mock_horizon, horizon_server_config):
    # Setup Mocks
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])

    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    dest_key = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    wallet = Wallet(
        id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True
    )
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
        amount=10.0,
    )

    # Verify
    assert result.success is False
    assert result.error_message == "Destination account does not exist"


@pytest.mark.asyncio
async def test_send_payment_checks_muxed_underlying_account_but_keeps_destination():
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = AsyncMock(spec=IStellarService)

    user_id = 123
    source_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    muxed_address = (
        "MCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYKAAAAAAAAAAXPAMAK"
    )
    underlying_address = "GCN57S4FDT6VSWM6EOWZKPDEDZRIA7PP7N4WSFRU6RZAD4LK52QYLQDJ"
    wallet = Wallet(
        id=1, user_id=user_id, public_key=source_key, is_default=True, is_free=True
    )
    mock_wallet_repo.get_default_wallet.return_value = wallet
    stellar_service.check_account_exists.return_value = True
    stellar_service.build_payment_transaction.return_value = "XDR_PAYMENT"

    use_case = SendPayment(mock_wallet_repo, stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        destination_address=muxed_address,
        destination_check_address=underlying_address,
        asset=Asset(code="XLM"),
        amount=10.0,
    )

    assert result.success is True
    stellar_service.check_account_exists.assert_awaited_once_with(underlying_address)
    stellar_service.build_payment_transaction.assert_awaited_once()
    assert (
        stellar_service.build_payment_transaction.await_args.kwargs[
            "destination_account_id"
        ]
        == muxed_address
    )


@pytest.mark.asyncio
async def test_send_payment_create_account(mock_horizon, horizon_server_config):
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])

    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    dest_key = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    wallet = Wallet(
        id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True
    )
    mock_wallet_repo.get_default_wallet.return_value = wallet

    # Destination does not exist yet
    mock_horizon.set_account(public_key)
    mock_horizon.set_not_found(dest_key)

    use_case = SendPayment(mock_wallet_repo, stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        destination_address=dest_key,
        asset=Asset(code="XLM"),
        amount=10.0,
        create_account=True,
    )

    assert result.success is True
    assert result.xdr is not None
    assert "AAAA" in result.xdr


@pytest.mark.asyncio
async def test_send_payment_formats_float_to_7_decimals(
    mock_horizon, horizon_server_config
):
    """Regression: raw str(float) could carry 17-significant-digit garbage
    into the payment op; amount must be normalized to 7 decimals."""
    from stellar_sdk import TransactionEnvelope, Network

    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])

    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    dest_key = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    wallet = Wallet(
        id=1, user_id=123, public_key=public_key, is_default=True, is_free=True
    )
    mock_wallet_repo.get_default_wallet.return_value = wallet

    mock_horizon.set_account(public_key)
    mock_horizon.set_account(dest_key)

    amount = 0.1 * 7  # 0.7000000000000001 as raw str
    use_case = SendPayment(mock_wallet_repo, stellar_service)
    result = await use_case.execute(
        user_id=123,
        destination_address=dest_key,
        asset=Asset(code="XLM"),
        amount=amount,
    )

    assert result.success is True
    envelope = TransactionEnvelope.from_xdr(
        result.xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
    )
    payment_op = envelope.transaction.operations[0]
    # stellar_sdk normalizes stroops back to string without trailing zeros
    assert payment_op.amount == "0.7"
    assert payment_op.amount != str(amount)


@pytest.mark.asyncio
async def test_create_cheque_success(mock_horizon, horizon_server_config):
    from core.use_cases.cheque.create_cheque import CreateCheque

    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])

    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    wallet = Wallet(
        id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True
    )
    mock_wallet_repo.get_default_wallet.return_value = wallet

    # Source exists
    mock_horizon.set_account(public_key)

    use_case = CreateCheque(mock_wallet_repo, stellar_service)
    result = await use_case.execute(user_id, amount=10.0, count=5, memo="UUID")

    assert result.success is True
    assert result.xdr is not None
    assert "AAAA" in result.xdr


@pytest.mark.asyncio
async def test_create_cheque_formats_float_product_to_7_decimals(
    mock_horizon, horizon_server_config
):
    """Regression: str(0.2 * 3) == '0.6000000000000001' broke stellar_sdk.

    Build must go through f'{total:.7f}' so the payment op carries a clean
    7-decimal amount instead of 17-significant-digit float garbage."""
    from core.use_cases.cheque.create_cheque import CreateCheque
    from stellar_sdk import TransactionEnvelope, Network

    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])

    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    wallet = Wallet(
        id=1, user_id=123, public_key=public_key, is_default=True, is_free=True
    )
    mock_wallet_repo.get_default_wallet.return_value = wallet

    mock_horizon.set_account(public_key)

    use_case = CreateCheque(mock_wallet_repo, stellar_service)
    result = await use_case.execute(123, amount=0.2, count=3, memo="chequeuuid16xx")

    assert result.success is True
    envelope = TransactionEnvelope.from_xdr(
        result.xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
    )
    payment_op = envelope.transaction.operations[0]
    # stellar_sdk normalizes stroops back to string without trailing zeros
    assert payment_op.amount == "0.6"
    assert payment_op.amount != str(0.2 * 3)
