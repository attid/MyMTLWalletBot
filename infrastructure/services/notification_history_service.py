"""
Notification History Service - stores sent notifications in memory with TTL.
Used for creating filters from recent notifications.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid

from db.models import TOperations


@dataclass
class NotificationRecord:
    """A record of a sent notification."""
    id: str
    operation_type: str
    asset_code: str
    amount: float
    wallet_id: int
    public_key: str
    created_at: datetime = field(default_factory=datetime.utcnow)


class NotificationHistoryService:
    """
    Stores recent notifications in memory for creating filters.

    - TTL: 12 hours by default
    - Max 50 records per user
    - Records are cleaned up on access
    """

    def __init__(self, ttl_hours: int = 12, max_per_user: int = 50):
        self._history: Dict[int, List[NotificationRecord]] = {}
        self._ttl = timedelta(hours=ttl_hours)
        self._max_per_user = max_per_user

    def add(self, user_id: int, operation: TOperations, wallet_id: int, public_key: str) -> None:
        """
        Add an operation to user's notification history.
        Should be called AFTER notification is successfully sent.
        """
        # Clean up old records first
        self._cleanup_user(user_id)

        # Initialize list if needed
        if user_id not in self._history:
            self._history[user_id] = []

        # Extract operation data
        try:
            amount = float(operation.amount1 or 0)
        except (ValueError, TypeError):
            amount = 0.0

        record = NotificationRecord(
            id=str(uuid.uuid4())[:8],
            operation_type=operation.operation or "",
            asset_code=operation.code1 or "XLM",
            amount=amount,
            wallet_id=wallet_id,
            public_key=public_key,
        )

        # Add to front (most recent first)
        self._history[user_id].insert(0, record)

        # Trim to max size
        if len(self._history[user_id]) > self._max_per_user:
            self._history[user_id] = self._history[user_id][:self._max_per_user]

    def get_recent(self, user_id: int, limit: int = 10) -> List[NotificationRecord]:
        """
        Get the most recent N notifications for a user.
        Returns empty list if no records found.
        """
        self._cleanup_user(user_id)

        records = self._history.get(user_id, [])
        return records[:limit]

    def get_by_id(self, user_id: int, record_id: str) -> Optional[NotificationRecord]:
        """Get a specific notification record by its ID."""
        self._cleanup_user(user_id)

        for record in self._history.get(user_id, []):
            if record.id == record_id:
                return record
        return None

    def _cleanup_user(self, user_id: int) -> None:
        """Remove expired records for a specific user."""
        if user_id not in self._history:
            return

        cutoff = datetime.utcnow() - self._ttl
        self._history[user_id] = [
            r for r in self._history[user_id]
            if r.created_at > cutoff
        ]

        # Remove empty lists
        if not self._history[user_id]:
            del self._history[user_id]

    def cleanup(self) -> None:
        """Remove all expired records across all users."""
        user_ids = list(self._history.keys())
        for user_id in user_ids:
            self._cleanup_user(user_id)
