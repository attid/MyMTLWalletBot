from __future__ import annotations

import base64
import hmac
import json
import os
from hashlib import sha256
from typing import Any, Optional

import cryptocode  # type: ignore
from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.interfaces.services import IEncryptionService
from other.config_reader import config


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


class EncryptionService(IEncryptionService):
    # Argon2 defaults selected from target-server benchmark.
    ARGON2_MEMORY_COST = 65536  # 64 MiB
    ARGON2_TIME_COST = 3
    ARGON2_PARALLELISM = 1
    ARGON2_HASH_LEN = 32

    def encrypt(self, data: str, key: str) -> str:
        return cryptocode.encrypt(data, key)

    def decrypt(self, encrypted_data: str, key: str) -> Optional[str]:
        result = cryptocode.decrypt(encrypted_data, key)
        if result is False:  # cryptocode returns False on failure
            return None
        return str(result)

    def encrypt_wallet_container(
        self,
        *,
        secret_key: str,
        seed_key: Optional[str],
        mode: str,
        wallet_kind: str,
        pin: Optional[str] = None,
    ) -> str:
        if mode not in {"free", "user"}:
            raise ValueError(f"Unsupported wallet crypto mode: {mode}")
        if mode == "user" and not pin:
            raise ValueError("pin is required for user mode encryption")

        salt = os.urandom(16)
        kid = "current"
        data_key = self._derive_key(
            mode=mode,
            salt=salt,
            pin=pin,
            kek=self._get_kek(kid),
        )

        secret_block = self._encrypt_block(secret_key, data_key)
        payload: dict[str, Any] = {
            "v": 2,
            "mode": mode,
            "wallet_kind": wallet_kind,
            "kid": kid,
            "salt": _b64_encode(salt),
            "secret": secret_block,
        }
        if mode == "user":
            payload["kdf"] = {
                "algo": "argon2id",
                "m": self.ARGON2_MEMORY_COST,
                "t": self.ARGON2_TIME_COST,
                "p": self.ARGON2_PARALLELISM,
                "hash_len": self.ARGON2_HASH_LEN,
            }
        if seed_key:
            payload["seed"] = self._encrypt_block(seed_key, data_key)

        return json.dumps(payload, separators=(",", ":"))

    def decrypt_wallet_secret(
        self,
        wallet_crypto_v2: str,
        *,
        pin: Optional[str] = None,
    ) -> Optional[str]:
        return self._decrypt_named_block(
            wallet_crypto_v2,
            block_name="secret",
            pin=pin,
        )

    def decrypt_wallet_seed(
        self,
        wallet_crypto_v2: str,
        *,
        pin: Optional[str] = None,
    ) -> Optional[str]:
        return self._decrypt_named_block(
            wallet_crypto_v2,
            block_name="seed",
            pin=pin,
        )

    def _decrypt_named_block(
        self,
        wallet_crypto_v2: str,
        *,
        block_name: str,
        pin: Optional[str],
    ) -> Optional[str]:
        payload = self.parse_wallet_container(wallet_crypto_v2)
        if not payload:
            return None

        block = payload.get(block_name)
        if not isinstance(block, dict):
            return None

        mode = payload.get("mode")
        if mode not in {"free", "user"}:
            return None

        salt_raw = payload.get("salt")
        if not isinstance(salt_raw, str):
            return None
        salt = _b64_decode(salt_raw)

        kid = payload.get("kid") if isinstance(payload.get("kid"), str) else "current"
        for kek in self._candidate_keks(kid):
            key = self._derive_key(mode=mode, salt=salt, pin=pin, kek=kek)
            if key is None:
                return None
            value = self._decrypt_block(block, key)
            if value is not None:
                return value
        return None

    def parse_wallet_container(self, wallet_crypto_v2: str) -> Optional[dict[str, Any]]:
        if not wallet_crypto_v2 or not isinstance(wallet_crypto_v2, str):
            return None
        try:
            payload = json.loads(wallet_crypto_v2)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("v") != 2:
            return None
        return payload

    def _encrypt_block(self, value: str, data_key: bytes) -> dict[str, str]:
        aesgcm = AESGCM(data_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, value.encode("utf-8"), None)
        return {"nonce": _b64_encode(nonce), "ct": _b64_encode(ciphertext)}

    def _decrypt_block(self, block: dict[str, Any], data_key: bytes) -> Optional[str]:
        nonce_raw = block.get("nonce")
        ct_raw = block.get("ct")
        if not isinstance(nonce_raw, str) or not isinstance(ct_raw, str):
            return None
        try:
            nonce = _b64_decode(nonce_raw)
            ciphertext = _b64_decode(ct_raw)
            aesgcm = AESGCM(data_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception:
            return None
        return plaintext.decode("utf-8")

    def _derive_key(
        self,
        *,
        mode: str,
        salt: bytes,
        pin: Optional[str],
        kek: str,
    ) -> Optional[bytes]:
        if mode == "free":
            return hmac.new(
                key=kek.encode("utf-8"),
                msg=b"wallet-free-v2:" + salt,
                digestmod=sha256,
            ).digest()

        if not pin:
            return None
        return hash_secret_raw(
            secret=(pin + "|" + kek).encode("utf-8"),
            salt=salt,
            time_cost=self.ARGON2_TIME_COST,
            memory_cost=self.ARGON2_MEMORY_COST,
            parallelism=self.ARGON2_PARALLELISM,
            hash_len=self.ARGON2_HASH_LEN,
            type=Type.ID,
        )

    def _candidate_keks(self, kid: str) -> list[str]:
        keys: list[str] = []
        if kid == "old":
            old = self._get_optional_old_kek()
            if old:
                keys.append(old)
            keys.append(self._get_kek("current"))
            return keys

        keys.append(self._get_kek("current"))
        old = self._get_optional_old_kek()
        if old:
            keys.append(old)
        return keys

    def _get_optional_old_kek(self) -> Optional[str]:
        old = (
            config.wallet_kek_old.get_secret_value() if config.wallet_kek_old else None
        )
        if old and old.strip():
            return old.strip()
        return None

    def _get_kek(self, kid: str) -> str:
        if kid == "old":
            old = self._get_optional_old_kek()
            if old:
                return old
        return config.wallet_kek.get_secret_value()
