"""Stellar-compatible libsodium sealed-box operations."""

from __future__ import annotations

import asyncio
import base64
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
import time

from nacl.bindings import crypto_sign_ed25519_pk_to_curve25519
from nacl.exceptions import CryptoError
from nacl.public import PublicKey, SealedBox
from stellar_sdk import Keypair

from core.interfaces.services import IStellarSealedBoxService


SEALED_BOX_OVERHEAD = 48
MAX_PLAINTEXT_BYTES = 10 * 1024 * 1024
MAX_CIPHERTEXT_BYTES = MAX_PLAINTEXT_BYTES + SEALED_BOX_OVERHEAD
MAX_BASE64_CIPHERTEXT_BYTES = ((MAX_CIPHERTEXT_BYTES + 2) // 3) * 4


class SealedBoxError(ValueError):
    """Base error for a rejected sealed-box operation."""


class SealedBoxDecryptionError(SealedBoxError):
    """The payload cannot be decrypted by the supplied key."""


class SealedBoxRateLimitError(SealedBoxError):
    """The user exceeded the in-process rolling operation limit."""


class SealedBoxSizeError(SealedBoxError):
    """The input exceeds the configured payload limit."""


class StellarSealedBoxService(IStellarSealedBoxService):
    """Encrypt and decrypt sealed boxes addressed by Stellar keys."""

    def __init__(
        self,
        *,
        max_operations: int = 10,
        window_seconds: float = 3600,
        max_concurrency: int = 4,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_operations = max_operations
        self._window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[int, deque[float]] = defaultdict(deque)
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @asynccontextmanager
    async def operation_slot(self, *, user_id: int) -> AsyncIterator[None]:
        """Count an attempt and bound concurrent cryptographic work."""
        now = self._clock()
        attempts = self._attempts[user_id]
        cutoff = now - self._window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= self._max_operations:
            raise SealedBoxRateLimitError("sealed-box operation limit exceeded")
        attempts.append(now)
        async with self._semaphore:
            yield

    async def encrypt(
        self, user_id: int, recipient_public_key: str, plaintext: bytes
    ) -> bytes:
        if len(plaintext) > MAX_PLAINTEXT_BYTES:
            raise SealedBoxSizeError("plaintext is too large")
        async with self.operation_slot(user_id=user_id):
            return await asyncio.to_thread(
                self._encrypt_sync, recipient_public_key, plaintext
            )

    async def decrypt(
        self, user_id: int, recipient_secret: str, payload: bytes
    ) -> bytes:
        if len(payload) > MAX_BASE64_CIPHERTEXT_BYTES:
            raise SealedBoxSizeError("ciphertext is too large")
        async with self.operation_slot(user_id=user_id):
            return await asyncio.to_thread(
                self._decrypt_raw_or_base64_sync, recipient_secret, payload
            )

    @staticmethod
    def _encrypt_sync(recipient_public_key: str, plaintext: bytes) -> bytes:
        keypair = Keypair.from_public_key(recipient_public_key)
        curve_public = crypto_sign_ed25519_pk_to_curve25519(keypair.raw_public_key())
        return SealedBox(PublicKey(curve_public)).encrypt(plaintext)

    @classmethod
    def _decrypt_raw_or_base64_sync(
        cls, recipient_secret: str, payload: bytes
    ) -> bytes:
        try:
            return cls._decrypt_sync(recipient_secret, payload)
        except (CryptoError, ValueError):
            pass

        try:
            decoded = base64.b64decode(payload.strip(), validate=True)
        except (ValueError, base64.binascii.Error):
            decoded = b""
        if len(decoded) < SEALED_BOX_OVERHEAD or len(decoded) > MAX_CIPHERTEXT_BYTES:
            raise SealedBoxDecryptionError("sealed-box decryption failed")
        try:
            return cls._decrypt_sync(recipient_secret, decoded)
        except (CryptoError, ValueError) as exc:
            raise SealedBoxDecryptionError("sealed-box decryption failed") from exc

    @staticmethod
    def _decrypt_sync(recipient_secret: str, ciphertext: bytes) -> bytes:
        if len(ciphertext) < SEALED_BOX_OVERHEAD:
            raise SealedBoxDecryptionError("sealed-box ciphertext is too short")
        if len(ciphertext) > MAX_CIPHERTEXT_BYTES:
            raise SealedBoxSizeError("ciphertext is too large")
        keypair = Keypair.from_secret(recipient_secret)
        if keypair.signing_key is None:
            raise SealedBoxDecryptionError("secret key is unavailable")
        return SealedBox(keypair.signing_key.to_curve25519_private_key()).decrypt(
            ciphertext
        )
