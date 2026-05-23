from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
import asyncio
import tomllib

from loguru import logger

from core.domain.value_objects import Asset
from core.models.anchor_asset import (
    AnchorAssetSupport,
    SepOperationSupport,
    SepProtocol,
    SepProtocolSupport,
)
from other.config_reader import config
from other.web_tools import http_session_manager


FetchJson = Callable[[str], Awaitable[dict[str, Any]]]
FetchText = Callable[[str], Awaitable[str]]


class AnchorDiscoveryService:
    """Discovers SEP-6/SEP-24 support for Stellar assets with a short TTL cache."""

    def __init__(
        self,
        *,
        fetch_json: FetchJson | None = None,
        fetch_text: FetchText | None = None,
        horizon_url: str | None = None,
        ttl: timedelta = timedelta(hours=1),
        request_timeout: float = 5.0,
    ) -> None:
        self._fetch_json = fetch_json or self._default_fetch_json
        self._fetch_text = fetch_text or self._default_fetch_text
        self._horizon_url = (horizon_url or config.horizon_url).rstrip("/")
        self._ttl = ttl
        self._request_timeout = request_timeout
        self._cache: dict[
            tuple[str, str], tuple[datetime, AnchorAssetSupport | None]
        ] = {}
        self._issuer_cache: dict[str, tuple[datetime, IssuerSepInfo | None]] = {}
        self._issuer_locks: dict[str, asyncio.Lock] = {}

    async def discover_assets(self, assets: list[Asset]) -> list[AnchorAssetSupport]:
        supported = []
        seen: set[tuple[str, str]] = set()
        for asset in assets:
            if asset.issuer is None:
                continue
            cache_key = (asset.code, asset.issuer)
            if cache_key in seen:
                continue
            seen.add(cache_key)
            support = await self.discover_asset_summary(asset)
            if support and support.supported_protocols:
                supported.append(support)
        return supported

    async def discover_asset_summary(self, asset: Asset) -> AnchorAssetSupport | None:
        if asset.issuer is None:
            return None
        issuer_info = await self._discover_issuer(asset.issuer)
        if issuer_info is None:
            return None

        sep6 = (
            SepProtocolSupport(
                protocol=SepProtocol.SEP6,
                transfer_server=issuer_info.sep6_url,
            )
            if issuer_info.sep6_url
            else None
        )
        sep24 = (
            SepProtocolSupport(
                protocol=SepProtocol.SEP24,
                transfer_server=issuer_info.sep24_url,
            )
            if issuer_info.sep24_url
            else None
        )
        support = AnchorAssetSupport(
            asset=asset,
            anchor_domain=issuer_info.home_domain,
            web_auth_endpoint=issuer_info.web_auth_endpoint,
            sep6=sep6,
            sep24=sep24,
        )
        if not support.supported_protocols:
            return None
        return support

    async def discover_asset(self, asset: Asset) -> AnchorAssetSupport | None:
        if asset.issuer is None:
            return None

        cache_key = (asset.code, asset.issuer)
        cached = self._cache.get(cache_key)
        if cached:
            cached_at, support = cached
            if datetime.now(UTC) - cached_at <= self._ttl:
                return support

        support = await self._discover_asset_uncached(asset)
        self._cache[cache_key] = (datetime.now(UTC), support)
        return support

    async def _discover_asset_uncached(self, asset: Asset) -> AnchorAssetSupport | None:
        assert asset.issuer is not None
        issuer_info = await self._discover_issuer(asset.issuer)
        if issuer_info is None:
            return None

        sep6_info, sep24_info = await asyncio.gather(
            self._load_protocol_info(issuer_info.sep6_url),
            self._load_protocol_info(issuer_info.sep24_url),
        )

        sep6 = self._protocol_support_from_info(
            SepProtocol.SEP6,
            issuer_info.sep6_url,
            sep6_info,
            asset.code,
        )
        sep24 = self._protocol_support_from_info(
            SepProtocol.SEP24,
            issuer_info.sep24_url,
            sep24_info,
            asset.code,
        )

        support = AnchorAssetSupport(
            asset=asset,
            anchor_domain=issuer_info.home_domain,
            web_auth_endpoint=issuer_info.web_auth_endpoint,
            sep6=sep6,
            sep24=sep24,
        )
        if not support.supported_protocols:
            return None
        return support

    async def _discover_issuer(self, issuer: str) -> "IssuerSepInfo | None":
        cached = self._issuer_cache.get(issuer)
        if cached:
            cached_at, info = cached
            if datetime.now(UTC) - cached_at <= self._ttl:
                return info

        lock = self._issuer_locks.setdefault(issuer, asyncio.Lock())
        async with lock:
            cached = self._issuer_cache.get(issuer)
            if cached:
                cached_at, info = cached
                if datetime.now(UTC) - cached_at <= self._ttl:
                    return info

            info = await self._discover_issuer_uncached(issuer)
            self._issuer_cache[issuer] = (datetime.now(UTC), info)
            return info

    async def _discover_issuer_uncached(self, issuer: str) -> "IssuerSepInfo | None":
        try:
            issuer_account = await self._fetch_json(
                f"{self._horizon_url}/accounts/{issuer}"
            )
            home_domain = issuer_account.get("home_domain")
            if not home_domain:
                return None

            toml_text = await self._fetch_text(
                f"https://{home_domain}/.well-known/stellar.toml"
            )
            toml_data = tomllib.loads(toml_text)
            sep6_url = toml_data.get("TRANSFER_SERVER")
            sep24_url = toml_data.get("TRANSFER_SERVER_SEP0024")
            web_auth_endpoint = toml_data.get("WEB_AUTH_ENDPOINT")

            return IssuerSepInfo(
                home_domain=home_domain,
                web_auth_endpoint=web_auth_endpoint,
                sep6_url=sep6_url.rstrip("/") if sep6_url else None,
                sep24_url=sep24_url.rstrip("/") if sep24_url else None,
            )
        except Exception as exc:
            logger.debug(f"SEP issuer discovery failed for {issuer}: {exc}")
            return None

    async def _load_protocol_info(
        self, transfer_server: str | None
    ) -> dict[str, Any] | None:
        if not transfer_server:
            return None
        try:
            return await self._fetch_json(f"{transfer_server.rstrip('/')}/info")
        except Exception as exc:
            logger.debug(f"SEP info discovery failed for {transfer_server}: {exc}")
            return None

    def _protocol_support_from_info(
        self,
        protocol: SepProtocol,
        transfer_server: str | None,
        info: dict[str, Any] | None,
        asset_code: str,
    ) -> SepProtocolSupport | None:
        if not transfer_server or info is None:
            return None

        deposit = self._operation_support(info.get("deposit", {}).get(asset_code))
        withdraw = self._operation_support(info.get("withdraw", {}).get(asset_code))
        transactions = info.get("transactions", {})
        transactions_enabled = bool(
            isinstance(transactions, dict) and transactions.get("enabled")
        )

        protocol_support = SepProtocolSupport(
            protocol=protocol,
            transfer_server=transfer_server.rstrip("/"),
            deposit=deposit,
            withdraw=withdraw,
            transactions_enabled=transactions_enabled,
        )
        if not protocol_support.has_user_actions:
            return None
        return protocol_support

    def _operation_support(self, raw: Any) -> SepOperationSupport | None:
        if not isinstance(raw, dict) or not raw.get("enabled"):
            return None
        return SepOperationSupport(
            enabled=True,
            min_amount=self._optional_float(raw.get("min_amount")),
            max_amount=self._optional_float(raw.get("max_amount")),
            fee_fixed=self._optional_float(raw.get("fee_fixed")),
            fee_percent=self._optional_float(raw.get("fee_percent")),
            fields=raw.get("fields"),
            types=raw.get("types"),
        )

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def _default_fetch_json(self, url: str) -> dict[str, Any]:
        response = await asyncio.wait_for(
            http_session_manager.get_web_request("GET", url, return_type="json"),
            timeout=self._request_timeout,
        )
        if response.status >= 400 or not isinstance(response.data, dict):
            raise ValueError(f"Unexpected JSON response from {url}: {response.status}")
        return response.data

    async def _default_fetch_text(self, url: str) -> str:
        response = await asyncio.wait_for(
            http_session_manager.get_web_request("GET", url),
            timeout=self._request_timeout,
        )
        if response.status >= 400 or not isinstance(response.data, str):
            raise ValueError(f"Unexpected text response from {url}: {response.status}")
        return response.data


class IssuerSepInfo:
    def __init__(
        self,
        *,
        home_domain: str,
        web_auth_endpoint: str | None,
        sep6_url: str | None,
        sep24_url: str | None,
    ) -> None:
        self.home_domain = home_domain
        self.web_auth_endpoint = web_auth_endpoint
        self.sep6_url = sep6_url
        self.sep24_url = sep24_url
