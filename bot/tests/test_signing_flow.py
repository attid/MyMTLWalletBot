"""Tests for biometric signing flow."""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone

import fakeredis.aioredis

from shared.schemas import PendingTxMessage, TxSignedMessage
from shared.constants import (
    QUEUE_TX_SIGNED,
    REDIS_TX_PREFIX,
    REDIS_TX_TTL,
    FIELD_USER_ID,
    FIELD_WALLET_ADDRESS,
    FIELD_UNSIGNED_XDR,
    FIELD_MEMO,
    FIELD_STATUS,
    FIELD_SIGNED_XDR,
    FIELD_CREATED_AT,
    STATUS_PENDING,
    STATUS_SIGNED,
)


class TestPendingTxMessage:
    """Tests for PendingTxMessage schema."""

    def test_create_pending_tx_message(self):
        """Should create PendingTxMessage with all required fields."""
        msg = PendingTxMessage(
            tx_id="123_abc12345",
            user_id=123,
            wallet_address="GXXX...",
            unsigned_xdr="AAAA...",
            memo="Send 100 XLM",
        )

        assert msg.tx_id == "123_abc12345"
        assert msg.user_id == 123
        assert msg.wallet_address == "GXXX..."
        assert msg.unsigned_xdr == "AAAA..."
        assert msg.memo == "Send 100 XLM"

    def test_pending_tx_message_to_dict(self):
        """Should serialize to dict correctly."""
        msg = PendingTxMessage(
            tx_id="123_abc12345",
            user_id=123,
            wallet_address="GXXX...",
            unsigned_xdr="AAAA...",
            memo="Send 100 XLM",
        )

        data = msg.model_dump()

        assert data == {
            "tx_id": "123_abc12345",
            "user_id": 123,
            "wallet_address": "GXXX...",
            "unsigned_xdr": "AAAA...",
            "memo": "Send 100 XLM",
        }


class TestTxSignedMessage:
    """Tests for TxSignedMessage schema."""

    def test_create_tx_signed_message(self):
        """Should create TxSignedMessage with required fields."""
        msg = TxSignedMessage(
            tx_id="123_abc12345",
            user_id=123,
        )

        assert msg.tx_id == "123_abc12345"
        assert msg.user_id == 123

    def test_tx_signed_message_from_dict(self):
        """Should deserialize from dict correctly."""
        data = {
            "tx_id": "123_abc12345",
            "user_id": 123,
        }

        msg = TxSignedMessage(**data)

        assert msg.tx_id == "123_abc12345"
        assert msg.user_id == 123


class TestConstants:
    """Tests for shared constants."""

    def test_queue_name(self):
        """Should have correct queue name."""
        assert QUEUE_TX_SIGNED == "tx_signed"

    def test_redis_prefix_and_ttl(self):
        """Should have correct Redis prefix and TTL."""
        assert REDIS_TX_PREFIX == "tx:"
        assert REDIS_TX_TTL == 600

    def test_field_names(self):
        """Should have correct field names."""
        assert FIELD_USER_ID == "user_id"
        assert FIELD_WALLET_ADDRESS == "wallet_address"
        assert FIELD_UNSIGNED_XDR == "unsigned_xdr"
        assert FIELD_MEMO == "memo"
        assert FIELD_STATUS == "status"
        assert FIELD_SIGNED_XDR == "signed_xdr"
        assert FIELD_CREATED_AT == "created_at"

    def test_status_values(self):
        """Should have correct status values."""
        assert STATUS_PENDING == "pending"
        assert STATUS_SIGNED == "signed"


class TestPublishPendingTx:
    """Tests for publish_pending_tx function using dependency injection."""

    @pytest.fixture
    def fake_redis(self):
        """Create a fake Redis client for testing."""
        return fakeredis.aioredis.FakeRedis()

    @pytest.mark.asyncio
    async def test_publish_pending_tx_generates_tx_id(self, fake_redis):
        """Should generate unique tx_id with user_id prefix."""
        from other.faststream_tools import publish_pending_tx

        tx_id = await publish_pending_tx(
            user_id=123,
            wallet_address="GXXX...",
            unsigned_xdr="AAAA...",
            memo="Test TX",
            redis_client=fake_redis,
        )

        # Check tx_id format
        assert tx_id.startswith("123_")
        assert len(tx_id) == 12  # "123_" + 8 chars

        await fake_redis.aclose()

    @pytest.mark.asyncio
    async def test_publish_pending_tx_stores_in_redis(self, fake_redis):
        """Should store TX data in Redis hash with TTL."""
        from other.faststream_tools import publish_pending_tx

        tx_id = await publish_pending_tx(
            user_id=123,
            wallet_address="GXXX...",
            unsigned_xdr="AAAA...",
            memo="Test TX",
            redis_client=fake_redis,
        )

        # Verify data was stored in Redis
        tx_key = f"tx:{tx_id}"
        stored_data = await fake_redis.hgetall(tx_key)

        # Decode bytes to strings for comparison
        decoded_data = {k.decode(): v.decode() for k, v in stored_data.items()}

        assert decoded_data[FIELD_USER_ID] == "123"
        assert decoded_data[FIELD_WALLET_ADDRESS] == "GXXX..."
        assert decoded_data[FIELD_UNSIGNED_XDR] == "AAAA..."
        assert decoded_data[FIELD_MEMO] == "Test TX"
        assert decoded_data[FIELD_STATUS] == STATUS_PENDING
        assert FIELD_CREATED_AT in decoded_data

        # Verify TTL was set
        ttl = await fake_redis.ttl(tx_key)
        assert ttl > 0
        assert ttl <= REDIS_TX_TTL

        await fake_redis.aclose()

    @pytest.mark.asyncio
    async def test_publish_pending_tx_raises_without_redis(self):
        """Should raise RuntimeError if redis_client is None and global not set."""
        from other.faststream_tools import publish_pending_tx

        with pytest.raises(RuntimeError, match="REDIS_CLIENT is not initialized"):
            await publish_pending_tx(
                user_id=123,
                wallet_address="GXXX...",
                unsigned_xdr="AAAA...",
                memo="Test TX",
                redis_client=None,
            )


class TestSigningHelpers:
    """Tests for signing_helpers module.

    NOTE: signing_mode not yet in DB, so is_local_signing always False,
    is_server_signing always True.
    """

    def test_is_local_signing_always_false(self):
        """Should return False (signing_mode not in DB yet)."""
        from other.signing_helpers import is_local_signing
        from core.domain.entities import Wallet

        wallet = Wallet(
            id=1,
            user_id=123,
            public_key="GXXX...",
            is_default=True,
            is_free=False,
        )

        assert is_local_signing(wallet) is False

    def test_is_server_signing_always_true(self):
        """Should return True (signing_mode not in DB yet)."""
        from other.signing_helpers import is_server_signing
        from core.domain.entities import Wallet

        wallet = Wallet(
            id=1,
            user_id=123,
            public_key="GXXX...",
            is_default=True,
            is_free=False,
        )

        assert is_server_signing(wallet) is True


class TestWebAppKeyboard:
    """Tests for webapp keyboard."""

    def test_webapp_sign_keyboard_structure(self):
        """Should create keyboard with sign button and cancel button."""
        from keyboards.webapp import webapp_sign_keyboard

        tx_id = "123_abc12345"
        keyboard = webapp_sign_keyboard(tx_id)

        assert len(keyboard.inline_keyboard) == 2

        # First row - Web App button
        assert len(keyboard.inline_keyboard[0]) == 1
        sign_btn = keyboard.inline_keyboard[0][0]
        assert sign_btn.text == "✍️ Подписать"
        assert sign_btn.web_app is not None
        assert f"tx={tx_id}" in sign_btn.web_app.url

        # Second row - Cancel button
        assert len(keyboard.inline_keyboard[1]) == 1
        cancel_btn = keyboard.inline_keyboard[1][0]
        assert cancel_btn.text == "Отмена"
        assert cancel_btn.callback_data == f"cancel_biometric_sign:{tx_id}"

    def test_webapp_import_key_keyboard_structure(self):
        """Should create keyboard with import button and cancel button."""
        from keyboards.webapp import webapp_import_key_keyboard

        wallet_address = "GXXX..."
        keyboard = webapp_import_key_keyboard(wallet_address)

        assert len(keyboard.inline_keyboard) == 2

        # First row - Web App button
        assert len(keyboard.inline_keyboard[0]) == 1
        import_btn = keyboard.inline_keyboard[0][0]
        assert import_btn.text == "🔑 Настроить подписание"
        assert import_btn.web_app is not None
        assert f"address={wallet_address}" in import_btn.web_app.url

        # Second row - Cancel button
        assert len(keyboard.inline_keyboard[1]) == 1
        cancel_btn = keyboard.inline_keyboard[1][0]
        assert cancel_btn.text == "Отмена"
        assert cancel_btn.callback_data == "cancel_import_key"
