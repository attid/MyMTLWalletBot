from types import SimpleNamespace

from db.db_pool import DbCheckoutTracker, db_checkout_owner


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_checkout_tracker_attributes_connection_age_to_update_owner() -> None:
    clock = FakeClock()
    tracker = DbCheckoutTracker(clock=clock)
    connection_record = SimpleNamespace(info={})

    with db_checkout_owner(user_id=42, update_type="CallbackQuery"):
        lease = tracker.start(connection_record, task_name="update-123")
    assert lease.task_name == "update-123"
    assert lease.user_id == 42
    assert lease.update_type == "CallbackQuery"
    clock.now = 75

    observation = tracker.finish(connection_record)

    assert observation is not None
    assert observation.elapsed_seconds == 75
    assert observation.task_name == "update-123"
    assert observation.user_id == 42
    assert observation.update_type == "CallbackQuery"


def test_checkout_tracker_discards_completed_lease() -> None:
    tracker = DbCheckoutTracker(clock=lambda: 10)
    connection_record = SimpleNamespace(info={})
    tracker.start(connection_record, task_name="worker")

    assert tracker.finish(connection_record) is not None
    assert tracker.finish(connection_record) is None


def test_checkout_tracker_supports_checkout_without_asyncio_task() -> None:
    tracker = DbCheckoutTracker(clock=lambda: 10)
    connection_record = SimpleNamespace(info={})

    tracker.start(connection_record)

    observation = tracker.finish(connection_record)
    assert observation is not None
    assert observation.task_name == "no-asyncio-task"
