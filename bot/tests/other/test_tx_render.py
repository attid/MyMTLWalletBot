from pathlib import Path

from stellar_sdk import Account, Asset, Network, TransactionBuilder
from stellar_sdk.operation.create_claimable_balance import Claimant

from other.tx_render import render_classic_ops

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "classic"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text().strip()


def test_set_options_add_signer():
    lines = render_classic_ops(_load("set_options_add_signer.xdr"))
    assert lines == ["SetOptions: подписант GDZX..ECHO (weight 3)"]


def test_payment_native():
    lines = render_classic_ops(_load("payment_native.xdr"))
    assert lines == ["Payment: 10.5 XLM → GDLT..AYXI"]


def test_multi_ops_all_supported_types():
    lines = render_classic_ops(_load("multi_ops.xdr"))
    assert lines == [
        "ChangeTrust: EURMTL (limit 1000000)",
        "ManageData: doc",
        "CreateAccount: GDUM..NSOZ (2.5 XLM)",
        "AccountMerge → GCXR..CRWD",
    ]


def test_garbage_xdr_returns_empty():
    assert render_classic_ops("not-an-xdr") == []


def test_unsupported_operation_is_skipped():
    # BumpSequence op is not rendered; result must be empty list, not crash.
    from stellar_sdk import Account, Network, TransactionBuilder

    acct = Account("GCXRRPWG7ARDC4IE5DE6UMRY4UN5GUG5THQI3FUR3HXVFALORCCXCRWD", 1)
    te = (
        TransactionBuilder(acct, Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=10000)
        .append_bump_sequence_op(bump_to=100)
        .build()
    )
    assert render_classic_ops(te.to_xdr()) == []


SOURCE = "GCXRRPWG7ARDC4IE5DE6UMRY4UN5GUG5THQI3FUR3HXVFALORCCXCRWD"
DESTINATION = "GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
ISSUER = "GACKTN5DAZGWXRWB2WLM6OPBDHAMT6SJNGLJZPQMEZBUR4JUGBX2UK7V"
MTL = Asset("MTL", ISSUER)


def _builder() -> TransactionBuilder:
    builder = TransactionBuilder(
        Account(SOURCE, 1), Network.PUBLIC_NETWORK_PASSPHRASE, 100
    )
    builder.set_timeout(30)
    return builder


def test_path_payment_strict_send_renders_send_asset_and_destination():
    builder = _builder()
    builder.append_path_payment_strict_send_op(
        destination=DESTINATION,
        send_asset=MTL,
        send_amount="5",
        dest_asset=Asset.native(),
        dest_min="1",
        path=[],
    )
    lines = render_classic_ops(builder.build().to_xdr())
    assert len(lines) == 1
    assert lines[0].startswith("PathPaymentStrictSend: 5 MTL")
    assert "min 1 XLM" in lines[0]
    assert f"→ {DESTINATION[:4]}..{DESTINATION[-4:]}" in lines[0]


def test_path_payment_strict_receive_renders_send_asset_and_destination():
    builder = _builder()
    builder.append_path_payment_strict_receive_op(
        destination=DESTINATION,
        send_asset=MTL,
        send_max="7",
        dest_asset=Asset.native(),
        dest_amount="2",
        path=[],
    )
    lines = render_classic_ops(builder.build().to_xdr())
    assert len(lines) == 1
    assert lines[0].startswith("PathPaymentStrictReceive: max 7 MTL")
    assert "2 XLM" in lines[0]
    assert f"→ {DESTINATION[:4]}..{DESTINATION[-4:]}" in lines[0]


def test_create_claimable_balance_renders_asset_and_claimant_count():
    builder = _builder()
    builder.append_create_claimable_balance_op(
        asset=MTL,
        amount="3",
        claimants=[Claimant(destination=DESTINATION)],
    )
    lines = render_classic_ops(builder.build().to_xdr())
    assert lines == ["CreateClaimableBalance: 3 MTL (1 получателей)"]
