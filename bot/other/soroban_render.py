"""Local Soroban invocation decoder for sign previews and free-wallet checks.

Ported from eurmtl.me/services/xdr_parser.py + other/stellar_soroban.py so the
bot does not have to proxy decoding through eurmtl.me/remote/decode.
"""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp
from loguru import logger
from stellar_sdk import (
    Account,
    Network,
    StrKey,
    TransactionBuilder,
    TransactionEnvelope,
)

SOROBAN_RPC_URL = "https://soroban-rpc.mainnet.stellar.gateway.fm"
TOKEN_NAME_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
TOKEN_NAME_CACHE_MAXSIZE = 256
SIMULATE_SOURCE_ACCOUNT = (
    "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
)


@dataclass
class SorobanInvocation:
    contract_id: str
    function_name: str
    depth: int  # 0 = root invocation from auth entry


def _decode_sc_symbol(symbol) -> str:
    raw = getattr(symbol, "sc_symbol", None)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(symbol)


def _decode_contract_address(address) -> str:
    try:
        return StrKey.encode_contract(address.contract_id.hash)
    except Exception:
        return address.contract_id.hash.hex()


def _decode_sc_string(sc_string) -> str:
    raw = getattr(sc_string, "sc_string", sc_string)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _decode_address_arg(val) -> Optional[str]:
    """Return G.../C... string for an SCVal of type address, else None."""
    if getattr(val, "type", None) is None or val.type.value != 18:
        return None
    addr = val.address
    if addr is None:
        return None
    if addr.type.value == 0 and addr.account_id is not None:
        ed = addr.account_id.account_id.ed25519.uint256
        return StrKey.encode_ed25519_public_key(ed)
    if addr.type.value == 1 and addr.contract_id is not None:
        return StrKey.encode_contract(addr.contract_id.hash)
    return None


def _decode_i128_amount(val) -> Optional[int]:
    i128 = getattr(val, "i128", None)
    if i128 is None:
        return None
    hi = i128.hi.int64
    lo = i128.lo.uint64
    return (hi << 64) + lo


def _shorten_contract(contract_id: str) -> str:
    if len(contract_id) < 10:
        return contract_id
    return contract_id[:4] + ".." + contract_id[-4:]


def _shorten_address(address: str) -> str:
    if len(address) < 10:
        return address
    return address[:4] + ".." + address[-4:]


def _format_amount(raw_amount: int, decimals: int = 7) -> str:
    scaled = raw_amount / (10**decimals)
    formatted = f"{scaled:.{decimals}f}".rstrip("0").rstrip(".")
    return formatted or "0"


class _AsyncTTLCache:
    def __init__(self, ttl_seconds: int, maxsize: int) -> None:
        self._ttl = ttl_seconds
        self._maxsize = maxsize
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str):
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.monotonic() - ts > self._ttl:
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value) -> None:
        async with self._lock:
            if len(self._store) >= self._maxsize:
                oldest_key = min(self._store, key=lambda k: self._store[k][0])
                self._store.pop(oldest_key, None)
            self._store[key] = (time.monotonic(), value)


_token_name_cache = _AsyncTTLCache(
    ttl_seconds=TOKEN_NAME_CACHE_TTL_SECONDS,
    maxsize=TOKEN_NAME_CACHE_MAXSIZE,
)


async def _simulate_name_call(contract_id: str) -> dict:
    src = Account(SIMULATE_SOURCE_ACCOUNT, 0)
    tx = (
        TransactionBuilder(
            source_account=src,
            base_fee=200,
            network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE,
        )
        .append_invoke_contract_function_op(
            contract_id=contract_id,
            function_name="name",
            parameters=[],
        )
        .set_timeout(0)
        .build()
    )
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "simulateTransaction",
        "params": {
            "xdrFormat": "json",
            "transaction": tx.to_xdr(),
            "authMode": "",
        },
    }
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(SOROBAN_RPC_URL, json=payload) as response:
            if response.status != 200:
                raise ValueError(f"Soroban RPC status {response.status}")
            data = await response.json()
    results = data.get("result", {}).get("results", [])
    if not results:
        raise ValueError("simulateTransaction returned no results")
    first = results[0]
    if "returnValueJson" in first:
        return first["returnValueJson"]
    if "xdr" in first:
        return {"xdr": first["xdr"]}
    raise ValueError("simulateTransaction returned unsupported result format")


def _extract_name_from_sim(result: dict) -> str:
    if "string" in result:
        return _normalize_contract_string(result["string"])
    xdr_value = result.get("xdr")
    if xdr_value:
        decoded = base64.b64decode(xdr_value)
        if len(decoded) >= 8:
            length = int.from_bytes(decoded[4:8], byteorder="big")
            return decoded[8 : 8 + length].decode("utf-8", errors="replace")
    raise ValueError("simulate result has no string")


def _normalize_contract_string(value: str) -> str:
    if "\\x" not in value:
        return value
    try:
        return (
            value.encode("latin-1")
            .decode("unicode_escape")
            .encode("latin-1")
            .decode("utf-8")
        )
    except Exception:
        return value


async def read_token_contract_display_name(contract_id: str) -> str:
    """Return token name for a Soroban token contract (cached).

    Falls back to a shortened contract id if the Soroban RPC call fails.
    """
    cached = await _token_name_cache.get(contract_id)
    if cached is not None:
        return cached  # type: ignore[return-value]
    try:
        sim_result = await _simulate_name_call(contract_id)
        raw_name = _extract_name_from_sim(sim_result)
        display = raw_name.split(":", 1)[0] if ":" in raw_name else raw_name
        if display == "native":
            display = "XLM"
        await _token_name_cache.set(contract_id, display)
        return display
    except Exception as exc:
        logger.debug(f"read_token_contract_display_name({contract_id}) failed: {exc}")
        fallback = _shorten_contract(contract_id)
        return fallback


def _iter_invocation(invocation, depth: int) -> list[SorobanInvocation]:
    out: list[SorobanInvocation] = []
    contract_fn = getattr(invocation.function, "contract_fn", None)
    if contract_fn is not None:
        out.append(
            SorobanInvocation(
                contract_id=_decode_contract_address(contract_fn.contract_address),
                function_name=_decode_sc_symbol(contract_fn.function_name),
                depth=depth,
            )
        )
    for sub in getattr(invocation, "sub_invocations", []) or []:
        out.extend(_iter_invocation(sub, depth + 1))
    return out


def iter_invoke_host_operations(envelope: TransactionEnvelope) -> list:
    return [
        op
        for op in envelope.transaction.operations
        if type(op).__name__ == "InvokeHostFunction"
    ]


def collect_soroban_invocations(
    envelope: TransactionEnvelope,
) -> list[SorobanInvocation]:
    """Flatten every auth invocation tree of every InvokeHostFunction op.

    Returns depth-annotated contract_id + function_name entries in DFS order.
    An auth entry's root invocation has depth=0; its sub_invocations depth=1, etc.
    """
    result: list[SorobanInvocation] = []
    for op in iter_invoke_host_operations(envelope):
        for auth_entry in getattr(op, "auth", []) or []:
            root = getattr(auth_entry, "root_invocation", None)
            if root is None:
                continue
            result.extend(_iter_invocation(root, 0))
    return result


def has_non_empty_sub_invocations(envelope: TransactionEnvelope) -> bool:
    for op in iter_invoke_host_operations(envelope):
        for auth_entry in getattr(op, "auth", []) or []:
            root = getattr(auth_entry, "root_invocation", None)
            if root is None:
                continue
            if getattr(root, "sub_invocations", None):
                return True
    return False


def is_invoke_host_safe_for_free(
    operation, forbidden_contract_id: str
) -> bool:
    """Return True if an InvokeHostFunction op is safe for a free wallet.

    Rules:
      - must have at least one auth entry with a non-empty sub_invocations list
      - every contract touched in the auth tree (root + all sub_invocations)
        must differ from ``forbidden_contract_id`` (the XLM Soroban wrapper)
      - every sub_invocation in the tree must be a ``transfer`` call
        (whitelist: transfer_from/approve/mint/burn/unknown → unsafe)
      - the root invocation's function name is not constrained (dapps call
        ``swap``/``deposit``/``capture`` etc. on their own contracts)
      - the root ``host_function.invoke_contract.contract_address`` must also
        differ from ``forbidden_contract_id``
    """
    hf = getattr(operation, "host_function", None)
    ic = getattr(hf, "invoke_contract", None) if hf is not None else None
    if ic is not None:
        root_contract = _decode_contract_address(ic.contract_address)
        if root_contract == forbidden_contract_id:
            return False

    auth_entries = getattr(operation, "auth", None) or []
    if not auth_entries:
        return False

    found_sub_invocation = False

    for auth_entry in auth_entries:
        root = getattr(auth_entry, "root_invocation", None)
        if root is None:
            return False

        root_fn = getattr(root.function, "contract_fn", None)
        if root_fn is not None:
            root_contract_id = _decode_contract_address(root_fn.contract_address)
            if root_contract_id == forbidden_contract_id:
                return False

        subs = getattr(root, "sub_invocations", None) or []
        if subs:
            found_sub_invocation = True

        if not _check_sub_invocations_recursive(subs, forbidden_contract_id):
            return False

    return found_sub_invocation


def _check_sub_invocations_recursive(
    sub_invocations, forbidden_contract_id: str
) -> bool:
    for sub in sub_invocations:
        contract_fn = getattr(sub.function, "contract_fn", None)
        if contract_fn is None:
            return False
        function_name = _decode_sc_symbol(contract_fn.function_name)
        if function_name != "transfer":
            return False
        contract_id = _decode_contract_address(contract_fn.contract_address)
        if contract_id == forbidden_contract_id:
            return False
        nested = getattr(sub, "sub_invocations", None) or []
        if nested and not _check_sub_invocations_recursive(nested, forbidden_contract_id):
            return False
    return True


async def _render_single_transfer(contract_fn) -> Optional[str]:
    args = list(contract_fn.args or [])
    if len(args) < 3:
        return None
    token_contract_id = _decode_contract_address(contract_fn.contract_address)
    source = _decode_address_arg(args[0])
    destination = _decode_address_arg(args[1])
    amount_raw = _decode_i128_amount(args[2])
    if source is None or destination is None or amount_raw is None:
        return None

    token_name = await read_token_contract_display_name(token_contract_id)
    amount_display = _format_amount(amount_raw)
    return (
        f"Transfer {amount_display} {token_name} "
        f"from {_shorten_address(source)} to {_shorten_address(destination)}"
    )


async def _render_invocation_transfers(invocation) -> list[str]:
    lines: list[str] = []
    for sub in getattr(invocation, "sub_invocations", []) or []:
        contract_fn = getattr(sub.function, "contract_fn", None)
        if contract_fn is not None:
            function_name = _decode_sc_symbol(contract_fn.function_name)
            if function_name == "transfer":
                rendered = await _render_single_transfer(contract_fn)
                if rendered:
                    lines.append(rendered)
        lines.extend(await _render_invocation_transfers(sub))
    return lines


async def render_soroban_sub_invocations(xdr: str) -> list[str]:
    """Render a human-readable summary of Soroban sub_invocation transfers.

    Returns an empty list when the XDR has no InvokeHostFunction with non-empty
    sub_invocations, or when none of the sub invocations are `transfer` calls.
    """
    try:
        envelope = TransactionEnvelope.from_xdr(
            xdr, network_passphrase=Network.PUBLIC_NETWORK_PASSPHRASE
        )
    except Exception as exc:
        logger.debug(f"render_soroban_sub_invocations: parse failed: {exc}")
        return []

    lines: list[str] = []
    for op in iter_invoke_host_operations(envelope):
        for auth_entry in getattr(op, "auth", []) or []:
            root = getattr(auth_entry, "root_invocation", None)
            if root is None:
                continue
            lines.extend(await _render_invocation_transfers(root))
    return lines
