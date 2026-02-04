"""WebApp for biometric transaction signing."""

import hashlib
import hmac
import os
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl

import redis.asyncio as aioredis
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from pydantic import BaseModel

from shared.constants import (
    REDIS_TX_PREFIX,
    FIELD_USER_ID,
    FIELD_WALLET_ADDRESS,
    FIELD_UNSIGNED_XDR,
    FIELD_MEMO,
    FIELD_STATUS,
    FIELD_SIGNED_XDR,
    STATUS_PENDING,
    STATUS_SIGNED,
    CHANNEL_TX_SIGNED,
)


# Config
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def validate_init_data(init_data: str) -> dict | None:
    """
    Validate Telegram WebApp initData.

    Returns parsed data if valid, None if invalid.
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN not set, skipping initData validation")
        return None

    try:
        # Parse init_data
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        hash_value = parsed.pop("hash", None)

        if not hash_value:
            return None

        # Create data-check-string
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )

        # Create secret key: HMAC-SHA256(bot_token, "WebAppData")
        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()

        # Calculate hash
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if calculated_hash != hash_value:
            logger.warning("initData hash mismatch")
            return None

        return parsed

    except Exception as e:
        logger.error(f"Failed to validate initData: {e}")
        return None


def get_user_id_from_init_data(init_data: str) -> int | None:
    """Extract and validate user_id from Telegram initData."""
    parsed = validate_init_data(init_data)
    if not parsed:
        return None

    try:
        import json
        user_data = json.loads(parsed.get("user", "{}"))
        return user_data.get("id")
    except Exception:
        return None


# Redis client
redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage Redis connection lifecycle."""
    global redis_client
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("WebApp started, Redis connected")
    yield
    if redis_client:
        await redis_client.aclose()
    logger.info("WebApp stopped")


app = FastAPI(title="MMWB WebApp", lifespan=lifespan)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# --- Models ---

class TxData(BaseModel):
    """Transaction data returned to frontend."""
    tx_id: str
    user_id: int
    wallet_address: str
    unsigned_xdr: str
    memo: str
    status: str


class SignRequest(BaseModel):
    """Request to submit signed transaction."""
    signed_xdr: str


# --- API Endpoints ---

@app.get("/api/tx/{tx_id}", response_model=TxData)
async def get_transaction(
    tx_id: str,
    x_telegram_init_data: str = Header(default=""),
):
    """Get transaction data from Redis. Validates that requester owns the TX."""
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")

    tx_key = f"{REDIS_TX_PREFIX}{tx_id}"
    tx_data = await redis_client.hgetall(tx_key)

    if not tx_data:
        raise HTTPException(status_code=404, detail="Transaction not found or expired")

    tx_user_id = int(tx_data.get(FIELD_USER_ID, 0))

    # Validate that requester is the TX owner
    if BOT_TOKEN and x_telegram_init_data:
        requester_id = get_user_id_from_init_data(x_telegram_init_data)
        if requester_id is None:
            raise HTTPException(status_code=401, detail="Invalid Telegram auth")
        if requester_id != tx_user_id:
            logger.warning(f"User {requester_id} tried to access TX of user {tx_user_id}")
            raise HTTPException(status_code=403, detail="Access denied")
    elif BOT_TOKEN:
        # BOT_TOKEN set but no initData provided
        raise HTTPException(status_code=401, detail="Telegram auth required")

    return TxData(
        tx_id=tx_id,
        user_id=tx_user_id,
        wallet_address=tx_data.get(FIELD_WALLET_ADDRESS, ""),
        unsigned_xdr=tx_data.get(FIELD_UNSIGNED_XDR, ""),
        memo=tx_data.get(FIELD_MEMO, ""),
        status=tx_data.get(FIELD_STATUS, "unknown"),
    )


@app.post("/api/tx/{tx_id}/sign")
async def submit_signed_transaction(
    tx_id: str,
    request: SignRequest,
    x_telegram_init_data: str = Header(default=""),
):
    """Submit signed transaction. Validates that requester owns the TX."""
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")

    tx_key = f"{REDIS_TX_PREFIX}{tx_id}"

    # Check TX exists and is pending
    tx_data = await redis_client.hgetall(tx_key)
    if not tx_data:
        raise HTTPException(status_code=404, detail="Transaction not found or expired")

    status = tx_data.get(FIELD_STATUS)
    if status != STATUS_PENDING:
        raise HTTPException(status_code=400, detail=f"Transaction already {status}")

    tx_user_id = int(tx_data.get(FIELD_USER_ID, 0))

    # Validate that requester is the TX owner
    if BOT_TOKEN and x_telegram_init_data:
        requester_id = get_user_id_from_init_data(x_telegram_init_data)
        if requester_id is None:
            raise HTTPException(status_code=401, detail="Invalid Telegram auth")
        if requester_id != tx_user_id:
            logger.warning(f"User {requester_id} tried to sign TX of user {tx_user_id}")
            raise HTTPException(status_code=403, detail="Access denied")
    elif BOT_TOKEN:
        raise HTTPException(status_code=401, detail="Telegram auth required")

    # Update TX with signed XDR
    await redis_client.hset(tx_key, mapping={
        FIELD_SIGNED_XDR: request.signed_xdr,
        FIELD_STATUS: STATUS_SIGNED,
    })

    # Publish event for bot to process
    await redis_client.publish(CHANNEL_TX_SIGNED, tx_id)

    logger.info(f"TX {tx_id} signed by user {tx_user_id}")
    return {"success": True, "tx_id": tx_id}


# --- HTML Pages ---

@app.get("/sign", response_class=HTMLResponse)
async def sign_page(request: Request, tx: str | None = None):
    """Render transaction signing page."""
    return templates.TemplateResponse("sign.html", {
        "request": request,
        "tx_id": tx,
    })


@app.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, address: str | None = None):
    """Render key import page."""
    return templates.TemplateResponse("import.html", {
        "request": request,
        "wallet_address": address,
    })


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
