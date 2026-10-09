"""Human-readable rendering of classic (non-Soroban) Stellar operations.

Used for sign_tools previews: eurmtl.me transactions carry a human
description, but any raw XDR can be summarized locally the same way
Soroban sub-invocations are summarized by other.soroban_render.
"""

from __future__ import annotations

from html import escape
from typing import Optional

from loguru import logger
from stellar_sdk import Network, TransactionEnvelope
from stellar_sdk.operation.account_merge import AccountMerge
from stellar_sdk.operation.change_trust import ChangeTrust
from stellar_sdk.operation.create_account import CreateAccount
from stellar_sdk.operation.manage_data import ManageData
from stellar_sdk.operation.payment import Payment
from stellar_sdk.operation.set_options import SetOptions


def _short_key(key: Optional[str]) -> str:
    if not key:
        return "?"
    if len(key) <= 12:
        return key
    return f"{key[:4]}..{key[-4:]}"


def _account_str(account) -> str:
    """MuxedAccount/str → G... string."""
    if isinstance(account, str):
        return _short_key(account)
    account_id = getattr(account, "account_id", None)
    if account_id:
        return _short_key(account_id)
    return _short_key(str(account))


def _asset_str(asset) -> str:
    if asset.is_native():
        return "XLM"
    code = getattr(asset, "code", None)
    if code is not None:
        return code
    # LiquidityPoolAsset has no .code — render pool shares compactly.
    return "LP-пул"


def _signer_key_str(signer_key) -> Optional[str]:
    """Decode SignerKey to a human string (G.../X.../T... when possible)."""
    encoded = getattr(signer_key, "encoded_signer_key", None)
    if isinstance(encoded, str) and encoded:
        return encoded
    return None


def _render_op(op) -> Optional[str]:
    """Render one classic operation to a single human-readable line.

    All externally-controlled strings (names, domains) are HTML-escaped:
    rendered lines are inserted into parse_mode="HTML" Telegram messages.
    """
    if isinstance(op, Payment):
        asset = _asset_str(op.asset)
        return f"Payment: {op.amount} {asset} → {_account_str(op.destination)}"
    if isinstance(op, CreateAccount):
        return (
            f"CreateAccount: {_account_str(op.destination)} ({op.starting_balance} XLM)"
        )
    if isinstance(op, SetOptions):
        signer = getattr(op, "signer", None)
        if signer is not None:
            key = _signer_key_str(signer.signer_key)
            weight = getattr(signer, "weight", "?")
            return f"SetOptions: подписант {_short_key(key)} (weight {weight})"
        if op.master_weight is not None:
            return f"SetOptions: master weight {op.master_weight}"
        if op.home_domain is not None:
            return f"SetOptions: home domain {escape(op.home_domain)}"
        if op.inflation_dest is not None:
            return f"SetOptions: inflation dest {_account_str(op.inflation_dest)}"
        if op.set_flags is not None or op.clear_flags is not None:
            return "SetOptions: flags"
        return "SetOptions"
    if isinstance(op, ChangeTrust):
        if op.limit == "0":
            return f"ChangeTrust: удалить trustline {_asset_str(op.asset)}"
        return f"ChangeTrust: {_asset_str(op.asset)} (limit {op.limit})"
    if isinstance(op, ManageData):
        suffix = "" if op.data_value is not None else " (удаление)"
        return f"ManageData: {escape(op.data_name)}{suffix}"
    if isinstance(op, AccountMerge):
        return f"AccountMerge → {_account_str(op.destination)}"
    return None


def render_classic_ops(xdr: str) -> list[str]:
    """Render a human-readable summary of classic Stellar operations.

    Returns an empty list when the XDR cannot be parsed or contains no
    supported operation types.
    """
    try:
        envelope = TransactionEnvelope.from_xdr(
            xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
        )
    except Exception as exc:
        logger.debug(f"render_classic_ops: parse failed: {exc}")
        return []

    lines: list[str] = []
    for op in envelope.transaction.operations:
        try:
            line = _render_op(op)
        except Exception as exc:
            # One exotic operation must not break the whole preview.
            logger.debug(f"render_classic_ops: op render failed: {exc}")
            line = None
        if line:
            lines.append(line)
    return lines
