"""Async SEP-10 / SEP-24 protocol client.

Transport-only adapter: no FSM, no database, no Telegram. The HTTP callable is
injected (`fetch_json`) so tests never touch the network, and so the facade in
`anchor_transaction_service.py` can keep the bot's existing session manager.

Behaviour follows the live-anchor findings recorded in
`../sep_anchor/docs/runbooks/live-sep24-golden-client.md`:

* `POST /transactions/{deposit,withdraw}/interactive` must send a JSON body
  `{asset_code, amount, account}`; form-encoded creation fails on modern
  anchors;
* asset codes are case-sensitive and must be echoed verbatim;
* the interactive response carries `{type, url, id}` and the `id` is required
  to read the transaction later.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

from loguru import logger

from core.models.sep24 import InteractiveSession, Sep10Challenge, Sep10Token
from other.web_tools import http_session_manager
from infrastructure.services.sep24.token_store import jwt_expires_at

FetchJson = Callable[..., Awaitable[dict[str, Any]]]


class AnchorTransactionRequestError(Exception):
    """Raised when an anchor returns an unexpected response."""

    def __init__(self, *, url: str, status: int, body: object) -> None:
        self.url = url
        self.status = status
        self.body = body
        super().__init__(f"Unexpected JSON response from {url}: {status}; body={body}")

    @property
    def is_auth_error(self) -> bool:
        return self.status == 401


class Sep24Client:
    """Thin SEP-10/SEP-24 protocol client with an injectable HTTP transport."""

    def __init__(
        self,
        *,
        fetch_json: FetchJson | None = None,
        request_timeout: float = 5.0,
    ) -> None:
        self._fetch_json = fetch_json or self._default_fetch_json
        self._request_timeout = request_timeout

    # ---------- SEP-10 ----------

    async def fetch_challenge(
        self,
        web_auth_endpoint: str | None,
        *,
        account: str,
        asset_code: str | None = None,
    ) -> Sep10Challenge:
        if not web_auth_endpoint:
            raise ValueError("SEP-10 WEB_AUTH_ENDPOINT is not available")
        params: dict[str, str] = {"account": account}
        if asset_code:
            params["asset_code"] = asset_code
        response = await self._fetch_json("GET", web_auth_endpoint, params=params)
        challenge_xdr = response.get("transaction")
        network_passphrase = response.get("network_passphrase")
        if not isinstance(challenge_xdr, str) or not isinstance(
            network_passphrase, str
        ):
            raise ValueError("SEP-10 challenge response is invalid")
        return Sep10Challenge(xdr=challenge_xdr, network_passphrase=network_passphrase)

    async def exchange_token(
        self, web_auth_endpoint: str | None, signed_challenge_xdr: str
    ) -> Sep10Token:
        if not web_auth_endpoint:
            raise ValueError("SEP-10 WEB_AUTH_ENDPOINT is not available")
        response = await self._fetch_json(
            "POST",
            web_auth_endpoint,
            data={"transaction": signed_challenge_xdr},
        )
        token = response.get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("SEP-10 token response is invalid")
        expires_at = response.get("expires_at")
        if isinstance(expires_at, int):
            expires_at_value: int | None = expires_at
        elif isinstance(expires_at, str) and expires_at.isdigit():
            expires_at_value = int(expires_at)
        else:
            expires_at_value = jwt_expires_at(token)
        return Sep10Token(token=token, expires_at=expires_at_value)

    # ---------- SEP-24 ----------

    async def create_interactive(
        self,
        transfer_server: str,
        *,
        direction: str,
        asset_code: str,
        account: str,
        amount: str | None = None,
        lang: str | None = None,
        token: str | None = None,
    ) -> InteractiveSession:
        if direction not in {"deposit", "withdraw"}:
            raise ValueError(f"Unsupported SEP-24 operation: {direction}")
        body: dict[str, Any] = {"asset_code": asset_code, "account": account}
        if amount:
            body["amount"] = amount
        if lang:
            body["lang"] = lang
        response = await self._fetch_json(
            "POST",
            f"{transfer_server.rstrip('/')}/transactions/{direction}/interactive",
            json=body,
            headers=_bearer(token),
        )
        url = response.get("url")
        if not isinstance(url, str) or not url:
            raise ValueError("SEP-24 interactive response did not include url")
        transaction_id = response.get("id")
        kind = response.get("type")
        return InteractiveSession(
            url=url,
            transaction_id=str(transaction_id) if transaction_id else None,
            kind=str(kind) if kind else None,
        )

    async def fetch_transaction(
        self,
        transfer_server: str,
        *,
        transaction_id: str,
        token: str | None = None,
        asset_code: str | None = None,
        lang: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"id": transaction_id}
        if asset_code:
            params["asset_code"] = asset_code
        if lang:
            params["lang"] = lang
        return await self._fetch_json(
            "GET",
            f"{transfer_server.rstrip('/')}/transaction",
            params=params,
            headers=_bearer(token),
        )

    async def fetch_transactions(
        self,
        transfer_server: str,
        *,
        asset_code: str,
        token: str | None = None,
    ) -> dict[str, Any]:
        return await self._fetch_json(
            "GET",
            f"{transfer_server.rstrip('/')}/transactions",
            params={"asset_code": asset_code},
            headers=_bearer(token),
        )

    # ---------- transport ----------

    async def _default_fetch_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = build_url(url, params)
        response = await asyncio.wait_for(
            http_session_manager.get_web_request(
                method,
                url,
                json=json,
                headers=headers,
                data=data,
                return_type="json",
            ),
            timeout=self._request_timeout,
        )
        if response.status >= 400 or not isinstance(response.data, dict):
            logger.debug(f"SEP request failed: {method} {url} -> {response.status}")
            raise AnchorTransactionRequestError(
                url=url,
                status=response.status,
                body=response.data,
            )
        return response.data


def build_url(url: str, params: dict[str, Any] | None) -> str:
    """Append query parameters without breaking an existing query string."""
    if not params:
        return url
    separator = "&" if "?" in url else "?"
    return url + separator + urlencode(params)


def _bearer(token: str | None) -> dict[str, str] | None:
    return {"Authorization": f"Bearer {token}"} if token else None
