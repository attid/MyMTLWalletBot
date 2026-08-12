import base64
import importlib.util
from pathlib import Path

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from shared.constants import (
    FIELD_SEALEDBOX_CIPHERTEXT,
    FIELD_SEALEDBOX_OUTPUT_FILENAME,
    FIELD_STATUS,
    FIELD_USER_ID,
    FIELD_WALLET_ADDRESS,
    QUEUE_SEALEDBOX_COMPLETED,
    REDIS_SEALEDBOX_PREFIX,
    STATUS_PENDING,
)


WEBAPP_APP_PATH = Path(__file__).resolve().parents[3] / "webapp" / "app.py"
SPEC = importlib.util.spec_from_file_location("mmwb_webapp_app", WEBAPP_APP_PATH)
assert SPEC is not None and SPEC.loader is not None
webapp_app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(webapp_app)


async def _store(redis, token: str, *, user_id: int = 42) -> None:
    await redis.hset(
        f"{REDIS_SEALEDBOX_PREFIX}{token}",
        mapping={
            FIELD_USER_ID: str(user_id),
            FIELD_WALLET_ADDRESS: "GACTIVE",
            FIELD_SEALEDBOX_CIPHERTEXT: base64.b64encode(b"cipher").decode(),
            FIELD_SEALEDBOX_OUTPUT_FILENAME: "report.pdf",
            FIELD_STATUS: STATUS_PENDING,
        },
    )


@pytest.fixture
def webapp_redis(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(webapp_app, "redis_client", redis)
    monkeypatch.setattr(webapp_app, "BOT_TOKEN", "configured")
    monkeypatch.setattr(webapp_app, "get_user_id_from_init_data", lambda _value: 42)
    return redis


@pytest.mark.asyncio
async def test_owner_can_fetch_metadata_and_raw_ciphertext(webapp_redis) -> None:
    await _store(webapp_redis, "token")

    metadata = await webapp_app.get_sealedbox_metadata("token", "valid")
    response = await webapp_app.get_sealedbox_ciphertext("token", "valid")

    assert metadata.wallet_address == "GACTIVE"
    assert metadata.output_filename == "report.pdf"
    assert isinstance(response, Response)
    assert response.body == b"cipher"
    await webapp_redis.aclose()


@pytest.mark.asyncio
async def test_foreign_user_cannot_fetch_request(webapp_redis, monkeypatch) -> None:
    await _store(webapp_redis, "token", user_id=77)

    with pytest.raises(HTTPException) as error:
        await webapp_app.get_sealedbox_metadata("token", "valid")

    assert error.value.status_code == 403
    await webapp_redis.aclose()


@pytest.mark.asyncio
async def test_request_is_rejected_when_telegram_auth_is_not_configured(
    webapp_redis, monkeypatch
) -> None:
    await _store(webapp_redis, "token")
    monkeypatch.setattr(webapp_app, "BOT_TOKEN", "")

    with pytest.raises(HTTPException) as error:
        await webapp_app.get_sealedbox_metadata("token", "")

    assert error.value.status_code == 503
    await webapp_redis.aclose()


@pytest.mark.asyncio
async def test_completion_queues_status_without_plaintext(webapp_redis) -> None:
    await _store(webapp_redis, "token")

    result = await webapp_app.complete_sealedbox("token", "valid")

    assert result == {"success": True}
    event = await webapp_redis.lpop(QUEUE_SEALEDBOX_COMPLETED)
    assert "token" in event
    assert "42" in event
    assert "plaintext" not in event
    await webapp_redis.aclose()


def test_sealedbox_page_contains_local_only_decryption_contract() -> None:
    template = Path(webapp_app.BASE_DIR) / "templates" / "sealedbox.html"
    script = Path(webapp_app.BASE_DIR) / "static" / "js" / "sealedbox.js"
    content = template.read_text(encoding="utf-8") + script.read_text(encoding="utf-8")

    assert "CryptoStorage.getKeyInfo" in content
    assert "crypto_box_seal_open" in content
    assert "/complete" in content
    assert 'fetchJson(`/api/sealedbox/${token}/complete`, {method: "POST"})' in content
    assert "body: plaintext" not in content
    assert 'id="save-file-button"' in content
    assert "new File(" in content
    assert "navigator.canShare({files: [decryptedFile]})" in content
    assert "navigator.share({files: [decryptedFile]" in content
    assert 'document.getElementById("plaintext-output").textContent' in content
    assert 'id="download-fallback"' in content
    assert 'window.addEventListener("pagehide", cleanupDownload)' in content
    assert "link.remove()" not in content
