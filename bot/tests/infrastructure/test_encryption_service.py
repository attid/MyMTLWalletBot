import json

import pytest
from infrastructure.services.encryption_service import EncryptionService


@pytest.fixture
def service():
    return EncryptionService()


def test_encryption_decryption_roundtrip(service):
    data = "my secret data"
    key = "my-secret-key"

    encrypted = service.encrypt(data, key)
    assert encrypted != data

    decrypted = service.decrypt(encrypted, key)
    assert decrypted == data


def test_decryption_with_wrong_key(service):
    data = "my secret data"
    key = "correct-key"
    wrong_key = "wrong-key"

    encrypted = service.encrypt(data, key)
    decrypted = service.decrypt(encrypted, wrong_key)

    assert decrypted is None


def test_decryption_of_invalid_data(service):
    invalid_data = "not encrypted data"
    key = "any-key"

    decrypted = service.decrypt(invalid_data, key)

    assert decrypted is None


def test_encryption_different_keys_produce_different_results(service):
    data = "my secret data"
    key1 = "key-1"
    key2 = "key-2"

    encrypted1 = service.encrypt(data, key1)
    encrypted2 = service.encrypt(data, key2)

    assert encrypted1 != encrypted2


def test_encryption_empty_string(service):
    data = ""
    key = "key"

    encrypted = service.encrypt(data, key)
    decrypted = service.decrypt(encrypted, key)

    assert decrypted == data


def test_wallet_crypto_v2_roundtrip_free(service):
    container = service.encrypt_wallet_container(
        secret_key="SSECRET",
        seed_key="seed words",
        mode="free",
        wallet_kind="stellar_free",
    )

    secret = service.decrypt_wallet_secret(container)
    seed = service.decrypt_wallet_seed(container)

    assert secret == "SSECRET"
    assert seed == "seed words"


def test_wallet_crypto_v2_roundtrip_user(service):
    container = service.encrypt_wallet_container(
        secret_key="SSECRET",
        seed_key="seed words",
        mode="user",
        wallet_kind="stellar_user",
        pin="123456",
    )

    secret = service.decrypt_wallet_secret(container, pin="123456")
    seed = service.decrypt_wallet_seed(container, pin="123456")

    assert secret == "SSECRET"
    assert seed == "seed words"


def test_wallet_crypto_v2_user_wrong_pin_fails(service):
    container = service.encrypt_wallet_container(
        secret_key="SSECRET",
        seed_key=None,
        mode="user",
        wallet_kind="stellar_user",
        pin="123456",
    )

    assert service.decrypt_wallet_secret(container, pin="000000") is None


def test_wallet_crypto_v2_tampered_ciphertext_fails(service):
    container = service.encrypt_wallet_container(
        secret_key="SSECRET",
        seed_key=None,
        mode="free",
        wallet_kind="stellar_free",
    )
    payload = service.parse_wallet_container(container)
    assert payload is not None
    payload["secret"]["ct"] = "AAAA"

    assert (
        service.decrypt_wallet_secret(json.dumps(payload, separators=(",", ":")))
        is None
    )
