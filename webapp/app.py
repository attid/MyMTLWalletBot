"""WebApp for biometric transaction signing."""

import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request
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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
async def get_transaction(tx_id: str):
    """Get transaction data from Redis."""
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")

    tx_key = f"{REDIS_TX_PREFIX}{tx_id}"
    tx_data = await redis_client.hgetall(tx_key)

    if not tx_data:
        raise HTTPException(status_code=404, detail="Transaction not found or expired")

    return TxData(
        tx_id=tx_id,
        user_id=int(tx_data.get(FIELD_USER_ID, 0)),
        wallet_address=tx_data.get(FIELD_WALLET_ADDRESS, ""),
        unsigned_xdr=tx_data.get(FIELD_UNSIGNED_XDR, ""),
        memo=tx_data.get(FIELD_MEMO, ""),
        status=tx_data.get(FIELD_STATUS, "unknown"),
    )


@app.post("/api/tx/{tx_id}/sign")
async def submit_signed_transaction(tx_id: str, request: SignRequest):
    """Submit signed transaction."""
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")

    tx_key = f"{REDIS_TX_PREFIX}{tx_id}"

    # Check TX exists and is pending
    status = await redis_client.hget(tx_key, FIELD_STATUS)
    if not status:
        raise HTTPException(status_code=404, detail="Transaction not found or expired")
    if status != STATUS_PENDING:
        raise HTTPException(status_code=400, detail=f"Transaction already {status}")

    # Update TX with signed XDR
    await redis_client.hset(tx_key, mapping={
        FIELD_SIGNED_XDR: request.signed_xdr,
        FIELD_STATUS: STATUS_SIGNED,
    })

    # Publish event for bot to process
    await redis_client.publish(CHANNEL_TX_SIGNED, tx_id)

    logger.info(f"TX {tx_id} signed and published")
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
