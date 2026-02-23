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
