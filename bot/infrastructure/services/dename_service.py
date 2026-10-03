"""Fail-closed DeName resolution for Stellar public-network payments."""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit

import aiohttp
from pydantic import BaseModel, ConfigDict, ValidationError
from stellar_sdk import StrKey

NAME_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\."
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
CONTRACT_RE = re.compile(r"^C[A-Z2-7]{55}$")
MAX_INDEX_AGE = timedelta(seconds=120)


class DeNameResolutionError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ResolvedDeName:
    name: str
    address: str


class _Records(BaseModel):
    model_config = ConfigDict(strict=True)
    forward: str | None


class _Name(BaseModel):
    model_config = ConfigDict(strict=True)
    fullName: str
    status: str
    expiration: datetime
    tldContractId: str
    lastEventLedger: int
    records: _Records


class _Stream(BaseModel):
    model_config = ConfigDict(strict=True)
    streamName: str
    contractId: str | None
    lastProcessedLedger: int
    status: str
    updatedAt: datetime


class _Indexer(BaseModel):
    model_config = ConfigDict(strict=True)
    streams: list[_Stream]


class DeNameService:
    def __init__(self, api_base_url: str | None):
        self.api_base_url = api_base_url.rstrip("/") if api_base_url else None
        if self.api_base_url:
            parsed = urlsplit(self.api_base_url)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.path != "/api/v1"
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "DENAME_API_BASE_URL must be a mainnet HTTPS /api/v1 URL"
                )

    async def resolve(self, value: str) -> ResolvedDeName:
        name = value.strip().lower()
        if not NAME_RE.fullmatch(name):
            raise DeNameResolutionError("invalid")
        if not self.api_base_url:
            raise DeNameResolutionError("unavailable")

        timeout = aiohttp.ClientTimeout(total=4, connect=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            raw_name = await self._get(session, f"/names/{quote(name)}")
            raw_indexer = await self._get(session, "/indexer/status")
        try:
            record = _Name.model_validate_json(json.dumps(raw_name))
            indexer = _Indexer.model_validate_json(json.dumps(raw_indexer))
        except (ValidationError, TypeError, ValueError) as exc:
            raise DeNameResolutionError("invalid_response") from exc

        now = datetime.now(timezone.utc)
        if record.fullName != name or not CONTRACT_RE.fullmatch(record.tldContractId):
            raise DeNameResolutionError("invalid_response")
        if record.status != "active" or not self._is_active_expiration(
            now, record.expiration
        ):
            raise DeNameResolutionError("inactive")
        address = record.records.forward
        if not address or not StrKey.is_valid_ed25519_public_key(address):
            raise DeNameResolutionError("unresolved")

        tld = name.split(".", 1)[1]
        expected_stream = f"tld-base:{tld}:{record.tldContractId}"
        streams = [
            stream
            for stream in indexer.streams
            if stream.streamName in ("root-registry", expected_stream)
        ]
        if {stream.streamName for stream in streams} != {
            "root-registry",
            expected_stream,
        }:
            raise DeNameResolutionError("stale")
        for stream in streams:
            if stream.status != "idle" or not self._is_recent(
                now, stream.updatedAt
            ):
                raise DeNameResolutionError("stale")
            if stream.streamName == expected_stream and (
                stream.contractId != record.tldContractId
                or stream.lastProcessedLedger < record.lastEventLedger
            ):
                raise DeNameResolutionError("stale")
        return ResolvedDeName(name=name, address=address)

    @staticmethod
    def _is_active_expiration(now: datetime, expiration: datetime) -> bool:
        return expiration.tzinfo is not None and expiration > now

    @staticmethod
    def _is_recent(now: datetime, updated_at: datetime) -> bool:
        return (
            updated_at.tzinfo is not None
            and timedelta(0) <= now - updated_at <= MAX_INDEX_AGE
        )

    async def _get(self, session: aiohttp.ClientSession, path: str) -> object:
        assert self.api_base_url is not None
        for attempt in range(2):
            try:
                async with session.get(f"{self.api_base_url}{path}") as response:
                    if response.status == 404:
                        raise DeNameResolutionError(
                            "unknown" if path.startswith("/names/") else "unavailable"
                        )
                    if response.status >= 500 and attempt == 0:
                        continue
                    if response.status != 200:
                        raise DeNameResolutionError("unavailable")
                    return await response.json()
            except (ValueError, aiohttp.ContentTypeError) as exc:
                raise DeNameResolutionError("invalid_response") from exc
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == 1:
                    raise DeNameResolutionError("unavailable") from exc
        raise DeNameResolutionError("unavailable")
