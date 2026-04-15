from pathlib import Path
from unittest.mock import patch

import pytest

from other.soroban_render import (
    collect_soroban_invocations,
    has_non_empty_sub_invocations,
    render_soroban_sub_invocations,
)
from stellar_sdk import Network, TransactionEnvelope

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "soroban"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text().strip()


def _envelope(name: str) -> TransactionEnvelope:
    return TransactionEnvelope.from_xdr(
        _load(name), network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
    )


@pytest.mark.parametrize(
    "fixture,expected_has_subs",
    [
        ("tx1_allow_single_transfer.xdr", True),
        ("tx2_deny_xlm_soroban.xdr", True),
        ("tx4_deny_no_subs.xdr", False),
        ("tx6_allow_multi_transfer.xdr", True),
        ("tx7_deny_non_transfer_burn.xdr", True),
    ],
)
def test_has_non_empty_sub_invocations(fixture, expected_has_subs):
    env = _envelope(fixture)
    assert has_non_empty_sub_invocations(env) is expected_has_subs


def test_collect_invocations_tx1_single_transfer():
    env = _envelope("tx1_allow_single_transfer.xdr")
    invs = collect_soroban_invocations(env)

    assert [inv.function_name for inv in invs] == ["capture", "transfer"]
    assert [inv.depth for inv in invs] == [0, 1]
    assert all(inv.contract_id.startswith("C") for inv in invs)


def test_collect_invocations_tx2_xlm_soroban_in_sub():
    env = _envelope("tx2_deny_xlm_soroban.xdr")
    invs = collect_soroban_invocations(env)

    xlm_contract = "CAS3J7GYLGXMF6TDJBBYYSE3HQ6BBSMLNUQ34T6TZMYMW2EVH34XOWMA"
    assert any(inv.contract_id == xlm_contract for inv in invs)
    assert any(inv.function_name == "transfer" for inv in invs)


def test_collect_invocations_tx4_no_sub_invocations():
    env = _envelope("tx4_deny_no_subs.xdr")
    invs = collect_soroban_invocations(env)

    assert [inv.depth for inv in invs] == [0]
    assert invs[0].function_name == "batch"


def test_collect_invocations_tx6_multi_transfer():
    env = _envelope("tx6_allow_multi_transfer.xdr")
    invs = collect_soroban_invocations(env)

    fn_names = [inv.function_name for inv in invs]
    assert fn_names[0] == "deposit"
    assert fn_names.count("transfer") == 2


def test_collect_invocations_tx7_burn_in_sub():
    env = _envelope("tx7_deny_non_transfer_burn.xdr")
    invs = collect_soroban_invocations(env)

    assert invs[0].function_name == "withdraw"
    assert any(inv.function_name == "burn" for inv in invs)
    assert not any(inv.function_name == "transfer" for inv in invs)


@pytest.mark.asyncio
async def test_render_tx1_transfer_summary():
    async def fake_name(contract_id):
        return "EURMTL"

    with patch(
        "other.soroban_render.read_token_contract_display_name",
        side_effect=fake_name,
    ):
        lines = await render_soroban_sub_invocations(_load("tx1_allow_single_transfer.xdr"))

    assert len(lines) == 1
    assert lines[0].startswith("Transfer ")
    assert "EURMTL" in lines[0]
    assert " from G" in lines[0]
    assert " to C" in lines[0] or " to CAFX.." in lines[0]


@pytest.mark.asyncio
async def test_render_tx6_multiple_transfers():
    async def fake_name(contract_id):
        return "TOK"

    with patch(
        "other.soroban_render.read_token_contract_display_name",
        side_effect=fake_name,
    ):
        lines = await render_soroban_sub_invocations(_load("tx6_allow_multi_transfer.xdr"))

    assert len(lines) == 2
    assert all(line.startswith("Transfer ") and "TOK" in line for line in lines)


@pytest.mark.asyncio
async def test_render_tx4_no_subs_returns_empty():
    lines = await render_soroban_sub_invocations(_load("tx4_deny_no_subs.xdr"))
    assert lines == []


@pytest.mark.asyncio
async def test_render_tx7_burn_skipped():
    lines = await render_soroban_sub_invocations(_load("tx7_deny_non_transfer_burn.xdr"))
    # burn is not transfer → no preview lines
    assert lines == []


@pytest.mark.asyncio
async def test_render_invalid_xdr_returns_empty():
    lines = await render_soroban_sub_invocations("not-a-real-xdr")
    assert lines == []
