from pathlib import Path

from other.tx_render import render_classic_ops

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "classic"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text().strip()


def test_set_options_add_signer():
    lines = render_classic_ops(_load("set_options_add_signer.xdr"))
    assert lines == [
        "SetOptions: подписант GDZXMBXSDFOVQ5PKXCJRC5CEUDWBLSSPVQMOLE4EAKLDHUBYKIIMECHO (weight 3)"
    ]


def test_payment_native():
    lines = render_classic_ops(_load("payment_native.xdr"))
    assert lines == [
        "Payment: 10.5 XLM → GDLTH4KKMA4R2JGKA7XKI5DLHJBUT42D5RHVK6SS6YHZZLHVLCWJAYXI"
    ]


def test_multi_ops_all_supported_types():
    lines = render_classic_ops(_load("multi_ops.xdr"))
    assert lines == [
        "ChangeTrust: EURMTL (limit 1000000)",
        "ManageData: doc",
        "CreateAccount: GDUMK6YJZ6ZC72CAMVHLUHLIFTNSLD7WFWO75Q3T2EOEW75XWH4PNSOZ (2.5 XLM)",
        "AccountMerge → GCXRRPWG7ARDC4IE5DE6UMRY4UN5GUG5THQI3FUR3HXVFALORCCXCRWD",
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
