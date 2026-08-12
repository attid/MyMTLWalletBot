import asyncio
import base64

import pytest
from nacl.bindings import crypto_sign_ed25519_pk_to_curve25519
from nacl.public import PublicKey, SealedBox
from stellar_sdk import Keypair

from infrastructure.services.stellar_sealedbox_service import (
    SealedBoxDecryptionError,
    SealedBoxRateLimitError,
    StellarSealedBoxService,
)


def _keypair(seed_byte: int) -> Keypair:
    return Keypair.from_raw_ed25519_seed(bytes([seed_byte]) * 32)


@pytest.mark.asyncio
async def test_encrypt_is_compatible_with_libsodium_sealed_box() -> None:
    keypair = _keypair(7)
    service = StellarSealedBoxService()

    ciphertext = await service.encrypt(1, keypair.public_key, b"hello")

    plaintext = SealedBox(keypair.signing_key.to_curve25519_private_key()).decrypt(
        ciphertext
    )
    assert plaintext == b"hello"
    assert len(ciphertext) == len(b"hello") + 48


@pytest.mark.asyncio
async def test_decrypt_accepts_external_raw_ciphertext() -> None:
    keypair = _keypair(9)
    curve_public = crypto_sign_ed25519_pk_to_curve25519(keypair.verify_key.encode())
    ciphertext = SealedBox(PublicKey(curve_public)).encrypt(b"external")
    service = StellarSealedBoxService()

    assert await service.decrypt(1, keypair.secret, ciphertext) == b"external"


@pytest.mark.asyncio
async def test_decrypt_falls_back_to_strict_base64() -> None:
    keypair = _keypair(11)
    service = StellarSealedBoxService()
    ciphertext = await service.encrypt(1, keypair.public_key, b"encoded")

    result = await service.decrypt(2, keypair.secret, base64.b64encode(ciphertext))

    assert result == b"encoded"


@pytest.mark.asyncio
async def test_decrypt_reports_one_controlled_error_for_wrong_key() -> None:
    recipient = _keypair(13)
    wrong = _keypair(14)
    service = StellarSealedBoxService()
    ciphertext = await service.encrypt(1, recipient.public_key, b"private")

    with pytest.raises(SealedBoxDecryptionError):
        await service.decrypt(2, wrong.secret, ciphertext)


@pytest.mark.asyncio
async def test_rolling_limit_counts_failed_decrypt_attempts() -> None:
    now = 100.0
    service = StellarSealedBoxService(
        max_operations=2,
        window_seconds=60,
        clock=lambda: now,
    )

    for _ in range(2):
        with pytest.raises(SealedBoxDecryptionError):
            await service.decrypt(8, _keypair(20).secret, b"not ciphertext")

    with pytest.raises(SealedBoxRateLimitError):
        await service.decrypt(8, _keypair(20).secret, b"not ciphertext")


@pytest.mark.asyncio
async def test_semaphore_bounds_concurrent_crypto_operations() -> None:
    service = StellarSealedBoxService(max_concurrency=1)
    entered = asyncio.Event()
    release = asyncio.Event()
    active = 0
    peak = 0

    async def operation() -> None:
        nonlocal active, peak
        async with service.operation_slot(user_id=1):
            active += 1
            peak = max(peak, active)
            entered.set()
            await release.wait()
            active -= 1

    first = asyncio.create_task(operation())
    await entered.wait()
    second = asyncio.create_task(operation())
    await asyncio.sleep(0)
    assert peak == 1
    release.set()
    await asyncio.gather(first, second)
    assert peak == 1
