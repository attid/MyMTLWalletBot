from datetime import datetime, timedelta
from unittest.mock import MagicMock

from infrastructure.services.notification_history_service import (
    NotificationHistoryService,
    NotificationRecord,
)


class TestNotificationRecord:
    """Tests for NotificationRecord dataclass."""

    def test_create_record(self):
        """Test creating a notification record."""
        record = NotificationRecord(
            id="abc123",
            operation_type="payment",
            asset_code="EURMTL",
            amount=100.0,
            wallet_id=1,
            public_key="GKEY",
        )
        assert record.id == "abc123"
        assert record.operation_type == "payment"
        assert record.asset_code == "EURMTL"
        assert record.amount == 100.0
        assert record.wallet_id == 1
        assert record.public_key == "GKEY"
        assert record.created_at is not None


class TestNotificationHistoryService:
    """Tests for NotificationHistoryService."""

    def test_init_defaults(self):
        """Test default initialization."""
        service = NotificationHistoryService()
        assert service._ttl == timedelta(hours=12)
        assert service._max_per_user == 50
        assert service._history == {}

    def test_init_custom(self):
        """Test custom initialization."""
        service = NotificationHistoryService(ttl_hours=24, max_per_user=100)
        assert service._ttl == timedelta(hours=24)
        assert service._max_per_user == 100

    def test_add_operation(self):
        """Test adding an operation to history."""
        service = NotificationHistoryService()

        operation = MagicMock()
        operation.operation = "payment"
        operation.display_asset_code = "EURMTL"
        operation.display_amount_value = "100.5"

        service.add(
            user_id=123,
            operation=operation,
            wallet_id=1,
            public_key="GKEY",
        )

        assert 123 in service._history
        assert len(service._history[123]) == 1

        record = service._history[123][0]
        assert record.operation_type == "payment"
        assert record.asset_code == "EURMTL"
        assert record.amount == 100.5
        assert record.wallet_id == 1
        assert record.public_key == "GKEY"

    def test_add_operation_with_none_amount(self):
        """Test adding operation with None amount."""
        service = NotificationHistoryService()

        operation = MagicMock()
        operation.operation = "payment"
        operation.display_asset_code = "XLM"
        operation.display_amount_value = None

        service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        record = service._history[123][0]
        assert record.amount == 0.0

    def test_add_operation_with_invalid_amount(self):
        """Test adding operation with invalid amount string."""
        service = NotificationHistoryService()

        operation = MagicMock()
        operation.operation = "payment"
        operation.display_asset_code = "XLM"
        operation.display_amount_value = "invalid"

        service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        record = service._history[123][0]
        assert record.amount == 0.0

    def test_add_multiple_operations(self):
        """Test adding multiple operations - newest first."""
        service = NotificationHistoryService()

        for i in range(3):
            operation = MagicMock()
            operation.operation = f"payment_{i}"
            operation.display_asset_code = "EURMTL"
            operation.display_amount_value = str(i * 10)
            service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        assert len(service._history[123]) == 3
        # Newest should be first
        assert service._history[123][0].operation_type == "payment_2"
        assert service._history[123][2].operation_type == "payment_0"

    def test_add_respects_max_per_user(self):
        """Test that max_per_user limit is respected."""
        service = NotificationHistoryService(max_per_user=5)

        for i in range(10):
            operation = MagicMock()
            operation.operation = f"payment_{i}"
            operation.display_asset_code = "EURMTL"
            operation.display_amount_value = "10"
            service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        assert len(service._history[123]) == 5
        # Should keep the 5 most recent
        assert service._history[123][0].operation_type == "payment_9"
        assert service._history[123][4].operation_type == "payment_5"

    def test_get_recent(self):
        """Test getting recent operations."""
        service = NotificationHistoryService()

        for i in range(5):
            operation = MagicMock()
            operation.operation = f"payment_{i}"
            operation.display_asset_code = "EURMTL"
            operation.display_amount_value = "10"
            service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        recent = service.get_recent(123, limit=3)
        assert len(recent) == 3
        assert recent[0].operation_type == "payment_4"

    def test_get_recent_empty(self):
        """Test getting recent from empty history."""
        service = NotificationHistoryService()
        recent = service.get_recent(123, limit=10)
        assert recent == []

    def test_get_recent_less_than_limit(self):
        """Test getting recent when fewer records exist than limit."""
        service = NotificationHistoryService()

        operation = MagicMock()
        operation.operation = "payment"
        operation.display_asset_code = "EURMTL"
        operation.display_amount_value = "10"
        service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        recent = service.get_recent(123, limit=10)
        assert len(recent) == 1

    def test_get_by_id(self):
        """Test getting a specific record by ID."""
        service = NotificationHistoryService()

        operation = MagicMock()
        operation.operation = "payment"
        operation.display_asset_code = "EURMTL"
        operation.display_amount_value = "10"
        service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        record_id = service._history[123][0].id
        found = service.get_by_id(123, record_id)

        assert found is not None
        assert found.id == record_id

    def test_get_by_id_not_found(self):
        """Test getting a non-existent record."""
        service = NotificationHistoryService()
        found = service.get_by_id(123, "nonexistent")
        assert found is None

    def test_get_by_id_wrong_user(self):
        """Test getting record for wrong user."""
        service = NotificationHistoryService()

        operation = MagicMock()
        operation.operation = "payment"
        operation.display_asset_code = "EURMTL"
        operation.display_amount_value = "10"
        service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        record_id = service._history[123][0].id
        found = service.get_by_id(456, record_id)

        assert found is None

    def test_cleanup_user_removes_expired(self):
        """Test that cleanup removes expired records."""
        service = NotificationHistoryService(ttl_hours=1)

        # Create an old record manually
        old_record = NotificationRecord(
            id="old",
            operation_type="payment",
            asset_code="EURMTL",
            amount=10.0,
            wallet_id=1,
            public_key="GKEY",
            created_at=datetime.utcnow() - timedelta(hours=2),
        )
        service._history[123] = [old_record]

        # Trigger cleanup via get_recent
        recent = service.get_recent(123, limit=10)

        assert recent == []
        assert 123 not in service._history

    def test_cleanup_keeps_fresh_records(self):
        """Test that cleanup keeps non-expired records."""
        service = NotificationHistoryService(ttl_hours=1)

        operation = MagicMock()
        operation.operation = "payment"
        operation.display_asset_code = "EURMTL"
        operation.display_amount_value = "10"
        service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        recent = service.get_recent(123, limit=10)
        assert len(recent) == 1

    def test_global_cleanup(self):
        """Test global cleanup method."""
        service = NotificationHistoryService(ttl_hours=1)

        # Add fresh record for user 123
        operation = MagicMock()
        operation.operation = "payment"
        operation.display_asset_code = "EURMTL"
        operation.display_amount_value = "10"
        service.add(user_id=123, operation=operation, wallet_id=1, public_key="GKEY")

        # Add old record for user 456
        old_record = NotificationRecord(
            id="old",
            operation_type="payment",
            asset_code="EURMTL",
            amount=10.0,
            wallet_id=1,
            public_key="GKEY",
            created_at=datetime.utcnow() - timedelta(hours=2),
        )
        service._history[456] = [old_record]

        service.cleanup()

        # User 123 should still have their record
        assert 123 in service._history
        assert len(service._history[123]) == 1

        # User 456's expired record should be removed
        assert 456 not in service._history

    def test_multiple_users(self):
        """Test that history is isolated per user."""
        service = NotificationHistoryService()

        for user_id in [123, 456, 789]:
            operation = MagicMock()
            operation.operation = f"payment_{user_id}"
            operation.display_asset_code = "EURMTL"
            operation.display_amount_value = "10"
            service.add(user_id=user_id, operation=operation, wallet_id=1, public_key="GKEY")

        assert len(service._history) == 3
        assert service.get_recent(123, limit=10)[0].operation_type == "payment_123"
        assert service.get_recent(456, limit=10)[0].operation_type == "payment_456"
        assert service.get_recent(789, limit=10)[0].operation_type == "payment_789"
