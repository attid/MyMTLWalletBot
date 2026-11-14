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

# Anchors occasionally drop a keep-alive connection on the first request; one
# retry turns that into a normal answer instead of a missing asset.
FETCH_ATTEMPTS = 2
FETCH_RETRY_DELAY_SECONDS = 0.4


class AnchorDiscoveryService:
    """Discovers SEP-6/SEP-24 support for Stellar assets with a short TTL cache."""

    def __init__(
        self,
        *,
        fetch_json: FetchJson | None = None,
        fetch_text: FetchText | None = None,
        horizon_url: str | None = None,
        ttl: timedelta = timedelta(hours=1),
        negative_ttl: timedelta = timedelta(seconds=60),
        request_timeout: float = 15.0,
        summary_timeout: float = 18.0,
        list_concurrency: int = 3,
    ) -> None:
        self._fetch_json = fetch_json or self._default_fetch_json
        self._fetch_text = fetch_text or self._default_fetch_text
        self._horizon_url = (horizon_url or config.horizon_url).rstrip("/")
        self._ttl = ttl
        self._negative_ttl = negative_ttl
        self._request_timeout = request_timeout
        self._summary_timeout = summary_timeout
        self._list_concurrency = max(1, list_concurrency)
        self._cache: dict[
            tuple[str, str], tuple[datetime, AnchorAssetSupport | None]
        ] = {}
        self._issuer_cache: dict[str, tuple[datetime, IssuerSepInfo | None]] = {}
        self._issuer_locks: dict[str, asyncio.Lock] = {}
        self._protocol_info_cache: dict[
            str, tuple[datetime, dict[str, Any] | None]
        ] = {}
        self._protocol_info_locks: dict[str, asyncio.Lock] = {}

    async def discover_assets(self, assets: list[Asset]) -> list[AnchorAssetSupport]:
        """Discover SEP support for many assets, one anchor chain per issuer.

        Assets are grouped by issuer so that the `horizon -> stellar.toml ->
        sep6/sep24 info` chain runs once per anchor instead of once per asset.
        Without the grouping every asset of the same issuer queued behind the
        same URL lock and the per-asset budget expired, silently dropping
        otherwise supported assets (observed live with USDM).
        """
        unique_assets: list[Asset] = []
        seen: set[tuple[str, str]] = set()
        for asset in assets:
            if asset.issuer is None:
                continue
            cache_key = (asset.code, asset.issuer)
            if cache_key in seen:
                continue
            seen.add(cache_key)
            unique_assets.append(asset)

        groups: dict[str, list[Asset]] = {}
        for asset in unique_assets:
            assert asset.issuer is not None
            groups.setdefault(asset.issuer, []).append(asset)

        semaphore = asyncio.Semaphore(self._list_concurrency)

        async def discover_group(
            issuer: str, group: list[Asset]
        ) -> list[AnchorAssetSupport]:
            async with semaphore:
                try:
                    return await asyncio.wait_for(
                        self.discover_anchor_assets(issuer, group),
                        timeout=self._summary_timeout,
                    )
                except TimeoutError:
                    logger.warning(
                        "SEP anchor discovery timed out for "
                        f"{issuer} ({', '.join(asset.code for asset in group)})"
                    )
                    return []

        batches = await asyncio.gather(
            *(discover_group(issuer, group) for issuer, group in groups.items()),
            return_exceptions=True,
        )

        found: dict[tuple[str, str], AnchorAssetSupport] = {}
        for batch in batches:
            if isinstance(batch, Exception):
                logger.warning(f"SEP anchor discovery failed: {batch}")
                continue
            for support in batch:
                if support.supported_protocols:
                    found[(support.asset.code, support.asset.issuer or "")] = support

        return [
            found[key]
            for asset in unique_assets
            if (key := (asset.code, asset.issuer or "")) in found
        ]

    async def discover_anchor_assets(
        self, issuer: str, assets: list[Asset]
    ) -> list[AnchorAssetSupport]:
        """Resolve one anchor and build support entries for its assets."""
        issuer_info = await self._discover_issuer(issuer)
        if issuer_info is None:
            return []

        sep6_info, sep24_info = await asyncio.gather(
            self._load_protocol_info(issuer_info.sep6_url),
            self._load_protocol_info(issuer_info.sep24_url),
        )

        supports: list[AnchorAssetSupport] = []
        for asset in assets:
            support = self._build_support(asset, issuer_info, sep6_info, sep24_info)
            if support is not None:
                supports.append(support)
        return supports

    def _build_support(
        self,
        asset: Asset,
        issuer_info: "IssuerSepInfo",
        sep6_info: dict[str, Any] | None,
        sep24_info: dict[str, Any] | None,
    ) -> AnchorAssetSupport | None:
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
            signing_key=issuer_info.signing_key,
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
        if cached and self._is_fresh(*cached):
            return cached[1]

        supports = await self.discover_anchor_assets(asset.issuer, [asset])
        support = supports[0] if supports else None
        self._cache[cache_key] = (datetime.now(UTC), support)
        return support

    async def _fetch_with_retry(self, fetch, url: str):
        """Call `fetch(url)` retrying once on a transient transport failure."""
        last_error: Exception | None = None
        for attempt in range(FETCH_ATTEMPTS):
            try:
                return await fetch(url)
            except Exception as exc:  # noqa: BLE001 - retried, then re-raised
                last_error = exc
                if attempt + 1 < FETCH_ATTEMPTS:
                    logger.debug(f"SEP fetch retry for {url}: {exc!r}")
                    await asyncio.sleep(FETCH_RETRY_DELAY_SECONDS)
        assert last_error is not None
        raise last_error

    def _is_fresh(self, cached_at: datetime, value: Any) -> bool:
        """Cache lifetime: full TTL for a hit, short TTL for a failed lookup.

        A transient anchor failure must not hide an asset for an hour, otherwise
        a single slow `/info` response drops the asset from `/assets` until the
        process restarts.
        """
        ttl = self._ttl if value is not None else self._negative_ttl
        return datetime.now(UTC) - cached_at <= ttl

    async def _discover_issuer(self, issuer: str) -> "IssuerSepInfo | None":
        cached = self._issuer_cache.get(issuer)
        if cached and self._is_fresh(*cached):
            return cached[1]

        lock = self._issuer_locks.setdefault(issuer, asyncio.Lock())
        async with lock:
            cached = self._issuer_cache.get(issuer)
            if cached and self._is_fresh(*cached):
                return cached[1]

            info = await self._discover_issuer_uncached(issuer)
            self._issuer_cache[issuer] = (datetime.now(UTC), info)
            return info

    async def _discover_issuer_uncached(self, issuer: str) -> "IssuerSepInfo | None":
        try:
            issuer_account = await self._fetch_with_retry(
                self._fetch_json, f"{self._horizon_url}/accounts/{issuer}"
            )
            home_domain = issuer_account.get("home_domain")
            if not home_domain:
                return None

            toml_text = await self._fetch_with_retry(
                self._fetch_text, f"https://{home_domain}/.well-known/stellar.toml"
            )
            toml_data = tomllib.loads(toml_text)
            sep6_url = toml_data.get("TRANSFER_SERVER")
            sep24_url = toml_data.get("TRANSFER_SERVER_SEP0024")
            web_auth_endpoint = toml_data.get("WEB_AUTH_ENDPOINT")
            signing_key = toml_data.get("SIGNING_KEY")

            return IssuerSepInfo(
                home_domain=home_domain,
                web_auth_endpoint=web_auth_endpoint,
                signing_key=signing_key if isinstance(signing_key, str) else None,
                sep6_url=sep6_url.rstrip("/") if sep6_url else None,
                sep24_url=sep24_url.rstrip("/") if sep24_url else None,
            )
        except Exception as exc:
            logger.warning(f"SEP issuer discovery failed for {issuer}: {exc!r}")
            return None

    async def _load_protocol_info(
        self, transfer_server: str | None
    ) -> dict[str, Any] | None:
        if not transfer_server:
            return None
        transfer_server = transfer_server.rstrip("/")
        cached = self._protocol_info_cache.get(transfer_server)
        if cached and self._is_fresh(*cached):
            return cached[1]

        lock = self._protocol_info_locks.setdefault(transfer_server, asyncio.Lock())
        async with lock:
            cached = self._protocol_info_cache.get(transfer_server)
            if cached and self._is_fresh(*cached):
                return cached[1]

            info = await self._load_protocol_info_uncached(transfer_server)
            self._protocol_info_cache[transfer_server] = (datetime.now(UTC), info)
            return info

    async def _load_protocol_info_uncached(
        self, transfer_server: str
    ) -> dict[str, Any] | None:
        try:
            return await self._fetch_with_retry(
                self._fetch_json, f"{transfer_server}/info"
            )
        except Exception as exc:
            logger.warning(f"SEP info discovery failed for {transfer_server}: {exc!r}")
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

        # Anchor asset codes are case-sensitive (`yXLM`), while the wallet knows
        # the code as it appears on-chain. Resolve the anchor's spelling once
        # and use it verbatim for `/info` lookups and protocol requests.
        resolved_code = self._resolve_asset_code(info, asset_code)
        if resolved_code is None:
            return None

        deposit = self._operation_support(info.get("deposit", {}).get(resolved_code))
        withdraw = self._operation_support(info.get("withdraw", {}).get(resolved_code))
        transactions = info.get("transactions", {})
        transactions_enabled = bool(
            isinstance(transactions, dict) and transactions.get("enabled")
        )

        protocol_support = SepProtocolSupport(
            protocol=protocol,
            transfer_server=transfer_server.rstrip("/"),
            asset_code=resolved_code,
            deposit=deposit,
            withdraw=withdraw,
            transactions_enabled=transactions_enabled,
        )
        if not protocol_support.has_user_actions:
            return None
        return protocol_support

    @staticmethod
    def _resolve_asset_code(info: dict[str, Any], asset_code: str) -> str | None:
        """Return the anchor spelling of `asset_code` (exact match preferred)."""
        keys: list[str] = []
        for section in ("deposit", "withdraw"):
            entries = info.get(section)
            if isinstance(entries, dict):
                keys.extend(key for key in entries if isinstance(key, str))
        if asset_code in keys:
            return asset_code
        for key in keys:
            if key.lower() == asset_code.lower():
                return key
        return None

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
        signing_key: str | None = None,
    ) -> None:
        self.home_domain = home_domain
        self.web_auth_endpoint = web_auth_endpoint
        self.signing_key = signing_key
        self.sep6_url = sep6_url
        self.sep24_url = sep24_url
