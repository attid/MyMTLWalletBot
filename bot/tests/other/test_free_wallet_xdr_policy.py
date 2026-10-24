"""Free-wallet XLM policy for PathPayment and CreateClaimableBalance XDR.

The free-wallet invariant is about the assets an operation actually spends:
PathPaymentStrictSend/Receive spend ``send_asset`` and CreateClaimableBalance
spends ``asset``. A signature or the transaction fee source must not be
mistaken for the effective operation source.
"""

from __future__ import annotations

import pytest
from stellar_sdk import (
    Account,
    Asset,
    Keypair,
    MuxedAccount,
    Network,
    TransactionBuilder,
    TransactionEnvelope,
)
from stellar_sdk.operation.create_claimable_balance import Claimant

from other.stellar_tools import FreeWalletPolicyError, stellar_check_xdr

FREE = Keypair.from_raw_ed25519_seed(bytes([1]) * 32)
OTHER = Keypair.from_raw_ed25519_seed(bytes([2]) * 32)
DESTINATION = Keypair.from_raw_ed25519_seed(bytes([3]) * 32).public_key
ISSUER = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"

XLM = Asset.native()
MTL = Asset("MTL", ISSUER)
MTLCROWD = Asset("MTLCROWD", ISSUER)


def _builder(source: str) -> TransactionBuilder:
    builder = TransactionBuilder(
        Account(source, 1),
        Network.PUBLIC_NETWORK_PASSPHRASE,
        100,
    )
    builder.set_timeout(30)
    return builder


def _path_send_xdr(
    send_asset: Asset,
    dest_asset: Asset = MTL,
    *,
    tx_source: str = FREE.public_key,
    op_source=None,
    path=None,
) -> str:
    builder = _builder(tx_source)
    builder.append_path_payment_strict_send_op(
        destination=DESTINATION,
        send_asset=send_asset,
        send_amount="1",
        dest_asset=dest_asset,
        dest_min="1",
        path=path or [],
        source=op_source,
    )
    return builder.build().to_xdr()


def _path_receive_xdr(
    send_asset: Asset,
    dest_asset: Asset = MTL,
    *,
    tx_source: str = FREE.public_key,
    op_source=None,
    path=None,
) -> str:
    builder = _builder(tx_source)
    builder.append_path_payment_strict_receive_op(
        destination=DESTINATION,
        send_asset=send_asset,
        send_max="1",
        dest_asset=dest_asset,
        dest_amount="1",
        path=path or [],
        source=op_source,
    )
    return builder.build().to_xdr()


def _claimable_balance_xdr(
    asset: Asset,
    *,
    tx_source: str = FREE.public_key,
    op_source=None,
) -> str:
    builder = _builder(tx_source)
    builder.append_create_claimable_balance_op(
        asset=asset,
        amount="1",
        claimants=[Claimant(destination=DESTINATION)],
        source=op_source,
    )
    return builder.build().to_xdr()


def _payment_xdr(
    asset: Asset, *, tx_source: str = FREE.public_key, op_source=None
) -> str:
    builder = _builder(tx_source)
    builder.append_payment_op(
        destination=DESTINATION,
        asset=asset,
        amount="1",
        source=op_source,
    )
    return builder.build().to_xdr()


def _fee_bump_xdr(inner_xdr: str) -> str:
    inner = TransactionEnvelope.from_xdr(inner_xdr, Network.PUBLIC_NETWORK_PASSPHRASE)
    envelope = TransactionBuilder.build_fee_bump_transaction(
        fee_source=OTHER.public_key,
        base_fee=200,
        inner_transaction_envelope=inner,
        network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
    )
    return envelope.to_xdr()


async def _assert_allowed(xdr: str, free_key: str = FREE.public_key) -> str:
    result = await stellar_check_xdr(
        xdr, for_free_account=True, free_wallet_public_key=free_key
    )
    assert result is not None
    return result


async def _assert_denied(xdr: str, free_key: str | None = FREE.public_key) -> None:
    with pytest.raises(FreeWalletPolicyError):
        await stellar_check_xdr(
            xdr, for_free_account=True, free_wallet_public_key=free_key
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("send_asset", "dest_asset"),
    [
        (MTL, XLM),
        (MTL, MTL),
        (MTLCROWD, XLM),
        (MTL, MTLCROWD),
    ],
)
async def test_path_send_non_native_send_asset_is_allowed(
    send_asset: Asset, dest_asset: Asset
):
    await _assert_allowed(_path_send_xdr(send_asset, dest_asset))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("send_asset", "dest_asset"),
    [
        (MTL, XLM),
        (MTL, MTL),
        (MTLCROWD, XLM),
    ],
)
async def test_path_receive_non_native_send_asset_is_allowed(
    send_asset: Asset, dest_asset: Asset
):
    await _assert_allowed(_path_receive_xdr(send_asset, dest_asset))


@pytest.mark.asyncio
@pytest.mark.parametrize("dest_asset", [XLM, MTL])
async def test_path_send_native_send_asset_from_free_wallet_is_denied(
    dest_asset: Asset,
):
    await _assert_denied(_path_send_xdr(XLM, dest_asset))


@pytest.mark.asyncio
@pytest.mark.parametrize("dest_asset", [XLM, MTL])
async def test_path_receive_native_send_asset_from_free_wallet_is_denied(
    dest_asset: Asset,
):
    await _assert_denied(_path_receive_xdr(XLM, dest_asset))


@pytest.mark.asyncio
async def test_path_intermediate_native_asset_is_not_a_spend():
    await _assert_allowed(_path_send_xdr(MTL, MTL, path=[XLM]))


@pytest.mark.asyncio
async def test_path_native_send_asset_with_other_effective_source_is_allowed():
    # The free wallet co-signs, but the operation source is another account.
    await _assert_allowed(_path_send_xdr(XLM, MTL, op_source=OTHER.public_key))


@pytest.mark.asyncio
async def test_path_receive_native_send_asset_with_other_effective_source_is_allowed():
    await _assert_allowed(_path_receive_xdr(XLM, MTL, op_source=OTHER.public_key))


@pytest.mark.asyncio
async def test_path_receive_native_send_asset_with_free_operation_source_is_denied():
    await _assert_denied(
        _path_receive_xdr(
            XLM, MTL, tx_source=OTHER.public_key, op_source=FREE.public_key
        )
    )


@pytest.mark.asyncio
async def test_path_receive_native_send_asset_with_muxed_free_source_is_denied():
    await _assert_denied(
        _path_receive_xdr(XLM, MTL, op_source=MuxedAccount(FREE.public_key, 42))
    )


@pytest.mark.asyncio
async def test_path_native_send_asset_with_other_transaction_source_is_allowed():
    await _assert_allowed(_path_send_xdr(XLM, MTL, tx_source=OTHER.public_key))


@pytest.mark.asyncio
async def test_path_native_send_asset_with_free_operation_source_is_denied():
    # Transaction source is another account, operation source is the free one.
    await _assert_denied(
        _path_send_xdr(XLM, MTL, tx_source=OTHER.public_key, op_source=FREE.public_key)
    )


@pytest.mark.asyncio
async def test_path_native_send_asset_with_muxed_free_source_is_denied():
    muxed_free = MuxedAccount(FREE.public_key, 42)
    await _assert_denied(_path_send_xdr(XLM, MTL, op_source=muxed_free))


@pytest.mark.asyncio
async def test_path_native_send_asset_with_muxed_other_source_is_allowed():
    muxed_other = MuxedAccount(OTHER.public_key, 42)
    await _assert_allowed(
        _path_send_xdr(XLM, MTL, tx_source=OTHER.public_key, op_source=muxed_other)
    )


@pytest.mark.asyncio
async def test_claimable_balance_non_native_asset_is_allowed():
    await _assert_allowed(_claimable_balance_xdr(MTL))


@pytest.mark.asyncio
async def test_claimable_balance_native_asset_from_free_wallet_is_denied():
    await _assert_denied(_claimable_balance_xdr(XLM))


@pytest.mark.asyncio
async def test_claimable_balance_native_asset_with_other_source_is_allowed():
    await _assert_allowed(
        _claimable_balance_xdr(
            XLM, tx_source=OTHER.public_key, op_source=OTHER.public_key
        )
    )


@pytest.mark.asyncio
async def test_claimable_balance_native_asset_with_muxed_free_source_is_denied():
    await _assert_denied(
        _claimable_balance_xdr(XLM, op_source=MuxedAccount(FREE.public_key, 42))
    )


@pytest.mark.asyncio
async def test_multi_op_native_path_with_free_source_is_denied():
    builder = _builder(FREE.public_key)
    builder.append_path_payment_strict_send_op(
        destination=DESTINATION,
        send_asset=XLM,
        send_amount="1",
        dest_asset=MTL,
        dest_min="1",
        path=[],
        source=OTHER.public_key,
    )
    builder.append_path_payment_strict_send_op(
        destination=DESTINATION,
        send_asset=XLM,
        send_amount="1",
        dest_asset=MTL,
        dest_min="1",
        path=[],
    )
    await _assert_denied(builder.build().to_xdr())


@pytest.mark.asyncio
async def test_multi_op_non_native_paths_are_allowed():
    builder = _builder(FREE.public_key)
    builder.append_path_payment_strict_send_op(
        destination=DESTINATION,
        send_asset=MTL,
        send_amount="1",
        dest_asset=XLM,
        dest_min="1",
        path=[],
    )
    builder.append_create_claimable_balance_op(
        asset=MTLCROWD,
        amount="1",
        claimants=[Claimant(destination=DESTINATION)],
    )
    await _assert_allowed(builder.build().to_xdr())


@pytest.mark.asyncio
async def test_missing_free_wallet_key_fails_closed_for_native_spend():
    await _assert_denied(_path_send_xdr(XLM), free_key=None)


@pytest.mark.asyncio
async def test_missing_free_wallet_key_still_allows_non_native_spend():
    await _assert_allowed(_path_send_xdr(MTL), free_key=None)


@pytest.mark.asyncio
async def test_payment_native_xlm_is_still_denied_even_from_other_source():
    await _assert_denied(_payment_xdr(XLM, op_source=OTHER.public_key))


@pytest.mark.asyncio
async def test_payment_non_native_is_allowed():
    await _assert_allowed(_payment_xdr(MTL))


@pytest.mark.asyncio
async def test_invalid_xdr_returns_none_instead_of_policy_error():
    result = await stellar_check_xdr(
        "AAAAAgAAAAA=",
        for_free_account=True,
        free_wallet_public_key=FREE.public_key,
    )
    assert result is None


@pytest.mark.asyncio
async def test_fee_bump_is_denied_for_free_wallet():
    await _assert_denied(_fee_bump_xdr(_path_send_xdr(MTL)))


@pytest.mark.asyncio
async def test_fee_bump_is_not_supported_for_paid_wallet():
    result = await stellar_check_xdr(
        _fee_bump_xdr(_path_send_xdr(MTL)), for_free_account=False
    )
    assert result is None


@pytest.mark.asyncio
async def test_mtlcrowd_donation_path_receive_from_free_wallet_is_allowed():
    """Regression for Docker3 #99: non-native send asset, XLM destination."""
    await _assert_allowed(_path_receive_xdr(MTL, XLM))
