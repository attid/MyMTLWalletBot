from pathlib import Path

from other.tx_render import render_classic_ops

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "classic"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text().strip()


def test_set_options_add_signer():
    lines = render_classic_ops(_load("set_options_add_signer.xdr"))
    assert lines == [
        "SetOptions: подписант GDZX..ECHO (weight 3)"
    ]


def test_payment_native():
    lines = render_classic_ops(_load("payment_native.xdr"))
    assert lines == [
        "Payment: 10.5 XLM → GDLT..AYXI"
    ]


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

    acct = Account(
        "GCXRRPWG7ARDC4IE5DE6UMRY4UN5GUG5THQI3FUR3HXVFALORCCXCRWD", 1
    )
    te = (
        TransactionBuilder(acct, Network.PUBLIC_NETWORK_PASSPHRASE, base_fee=10000)
        .append_bump_sequence_op(bump_to=100)
        .build()
    )
    assert render_classic_ops(te.to_xdr()) == []
