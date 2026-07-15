import inspect

import pytest
from unittest.mock import AsyncMock
from stellar_sdk import Asset as SdkAsset, Network, TransactionEnvelope
from core.interfaces.repositories import IWalletRepository
from core.domain.entities import Wallet
from core.domain.value_objects import Asset
from core.use_cases.trade.swap_assets import SwapAssets
from core.use_cases.trade.manage_offer import ManageOffer
from infrastructure.services.stellar_service import StellarService


@pytest.mark.asyncio
async def test_swap_assets_success(mock_horizon, horizon_server_config):
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])

    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    wallet = Wallet(
        id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True
    )
    mock_wallet_repo.get_default_wallet.return_value = wallet

    # Configure mock_horizon to provide source account
    mock_horizon.set_account(public_key)

    VALID_ISSUER = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    use_case = SwapAssets(mock_wallet_repo, stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        send_asset=Asset(code="XLM"),
        send_amount=10.0,
        receive_asset=Asset(code="EURMTL", issuer=VALID_ISSUER),
        receive_amount=20.0,
        strict_receive=False,
    )

    assert result.success is True
    assert result.xdr is not None
    envelope = TransactionEnvelope.from_xdr(
        result.xdr, Network.PUBLIC_NETWORK_PASSPHRASE
    )
    assert envelope.transaction.operations[0].path == []


@pytest.mark.asyncio
@pytest.mark.parametrize("strict_receive", [False, True])
async def test_swap_assets_preserves_intermediate_path_in_xdr(
    mock_horizon, horizon_server_config, strict_receive
):
    assert "path" in inspect.signature(SwapAssets.execute).parameters

    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    mock_wallet_repo.get_default_wallet.return_value = Wallet(
        id=1, user_id=123, public_key=public_key, is_default=True, is_free=True
    )
    mock_horizon.set_account(public_key)

    issuer = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    result = await SwapAssets(mock_wallet_repo, stellar_service).execute(
        user_id=123,
        send_asset=Asset(code="USDM", issuer=issuer),
        send_amount=2.0,
        receive_asset=Asset(code="MTL", issuer=issuer),
        receive_amount=0.23,
        path=[Asset(code="SATSMTL", issuer=issuer)],
        strict_receive=strict_receive,
    )

    assert result.success is True
    envelope = TransactionEnvelope.from_xdr(
        result.xdr, Network.PUBLIC_NETWORK_PASSPHRASE
    )
    operation = envelope.transaction.operations[0]
    assert operation.path == [SdkAsset("SATSMTL", issuer)]


@pytest.mark.asyncio
async def test_manage_offer_success(mock_horizon, horizon_server_config):
    mock_wallet_repo = AsyncMock(spec=IWalletRepository)
    stellar_service = StellarService(horizon_url=horizon_server_config["url"])

    user_id = 123
    public_key = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    wallet = Wallet(
        id=1, user_id=user_id, public_key=public_key, is_default=True, is_free=True
    )
    mock_wallet_repo.get_default_wallet.return_value = wallet

    # Configure mock_horizon to provide source account
    mock_horizon.set_account(public_key)

    VALID_ISSUER = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
    use_case = ManageOffer(mock_wallet_repo, stellar_service)
    result = await use_case.execute(
        user_id=user_id,
        selling=Asset(code="XLM"),
        buying=Asset(code="EURMTL", issuer=VALID_ISSUER),
        amount=10.0,
        price=2.0,
    )

    assert result.success is True
    assert result.xdr is not None
    assert "AAAA" in result.xdr
