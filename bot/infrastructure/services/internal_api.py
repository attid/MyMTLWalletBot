"""Internal read-only HTTP API for trusted local services.

Exposes `GET /api/v1/address/{username}`: Telegram username -> wallet address.
Auth: static bearer-style token in the `X-Api-Token` header, constant-time
comparison. The server binds to loopback (or a docker network address) and is
never published externally. Follows the in-process aiohttp pattern already
used by NotificationService.start_server().
"""

import re
import secrets
from typing import Optional

from aiohttp import web
from loguru import logger
from sqlalchemy import select

from db.db_pool import db_pool
from db.models import MyMtlWalletBot, MyMtlWalletBotUsers

# Telegram usernames: letters, digits, underscores, up to 32 chars.
# Validated on the PRE-lowercase form: A-Z must be allowed here so that
# "Alice" reaches .lower(); restricting to a-z would 404 mixed case.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")

# Stellar account public keys are exactly 56 chars starting with 'G'.
_ADDRESS_LEN = 56


def normalize_username(raw: str) -> str:
    """Usernames are stored lowercase without the leading '@'.

    Only ONE leading '@' is stripped: additional '@' characters stay in
    the value. Validation happens BEFORE .lower() (ASCII regex), so
    Unicode look-alikes (e.g. U+212A 'K' folding to 'k') can never
    survive: .lower() over an ASCII [A-Za-z0-9_] string can only fold
    A-Z, never map a rejected char to a valid one.
    """
    cleaned = raw.removeprefix("@")
    if not _USERNAME_RE.fullmatch(cleaned):
        return ""
    return cleaned.lower()


def _is_public_key(value: str) -> bool:
    """Stellar public keys start with 'G'; secret seeds also have 56 chars
    but start with 'S' — never treat them as a payable address."""
    return len(value) == _ADDRESS_LEN and value.startswith("G")


class InternalApi:
    def __init__(self, token: str):
        self._token = token
        self._runner: Optional[web.AppRunner] = None

    def create_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/api/v1/address/{username}", self.handle_address)
        return app

    async def start(self, host: str, port: int) -> None:
        if self._runner is not None:
            raise RuntimeError("Internal API server is already running")
        runner = web.AppRunner(self.create_app())
        await runner.setup()
        try:
            await web.TCPSite(runner, host, port).start()
        except Exception:
            # A failed bind must not leak a live AppRunner.
            await runner.cleanup()
            raise
        self._runner = runner
        logger.info(f"Internal API listening on {host}:{port}")

    async def stop(self) -> None:
        # Take the reference and clear the field before awaiting: a
        # concurrent second stop() must not enter cleanup() on the same
        # runner again.
        runner = self._runner
        self._runner = None
        if runner:
            await runner.cleanup()
            logger.info("Internal API stopped")

    async def handle_address(self, request: web.Request) -> web.Response:
        provided = request.headers.get("X-Api-Token", "")
        # compare_digest on str rejects non-ASCII with TypeError (-> 500);
        # compare bytes so a garbage header is a plain 401.
        if not provided or not secrets.compare_digest(
            provided.encode("utf-8"), self._token.encode("utf-8")
        ):
            return web.json_response({"error": "unauthorized"}, status=401)

        username = normalize_username(request.match_info["username"])
        # Empty usernames exist in DB (users without a Telegram username are
        # stored with user_name = ""); never match them via a bare "@" request.
        # normalize_username returns "" for anything that fails validation.
        if not username:
            return web.json_response({"error": "not_found"}, status=404)

        try:
            async with db_pool.get_session() as session:
                row = (
                    await session.execute(
                        select(
                            MyMtlWalletBotUsers.user_id,
                            MyMtlWalletBotUsers.default_address,
                        )
                        .where(MyMtlWalletBotUsers.user_name == username)
                        .order_by(MyMtlWalletBotUsers.user_id.desc())
                        .limit(1)
                    )
                ).first()
                if row is None:
                    return web.json_response({"error": "not_found"}, status=404)
                user_id, raw_address = row
                address = raw_address.strip() if raw_address else ""

                # Second step (mirrors the bot's wallet logic): no usable
                # custom address -> fall back to the user's default wallet.
                if not _is_public_key(address):
                    wallet_row = (
                        await session.execute(
                            select(MyMtlWalletBot.public_key)
                            .where(MyMtlWalletBot.user_id == user_id)
                            .where(MyMtlWalletBot.default_wallet == 1)
                            .where(MyMtlWalletBot.need_delete == 0)
                            .order_by(MyMtlWalletBot.id.desc())
                            .limit(1)
                        )
                    ).first()
                    if wallet_row is not None and wallet_row[0]:
                        address = wallet_row[0].strip()
        except Exception as e:
            logger.opt(exception=e).error(
                f"Internal API DB error for username={username!r}"
            )
            return web.json_response({"error": "internal"}, status=500)

        if not _is_public_key(address):
            # Single 404 for "no such user" and "no usable address": the API
            # must not reveal whether a username is registered.
            return web.json_response({"error": "not_found"}, status=404)
        return web.json_response({"username": username, "address": address})
