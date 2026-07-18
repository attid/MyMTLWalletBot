# Notification Delivery Timeout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task.

**Goal:** Prevent a stuck Telegram notification send from retaining its Redis
flush lock and a handler's database session indefinitely.

**Architecture:** Apply a local 30-second timeout at the notification coordinator
sender boundary. Preserve the durable queue head on timeout, rely on the existing
token-owned `finally` cleanup, and improve plain-text operational diagnostics.
Treat Telegram's identical badge markup response as an idempotent no-op.

**Tech Stack:** Python 3.12 asyncio, Loguru, aiogram, Redis/fakeredis, pytest.

---

### Task 1: Bound a stuck notification sender

**Files:**

- Modify: `bot/tests/infrastructure/test_notification_coordinator.py`
- Modify: `bot/infrastructure/services/notification_coordinator.py`

1. Add a test sender that waits forever and records cancellation.
2. Run the focused test and verify RED because delivery has no timeout.
3. Add an injected positive finite delivery timeout with a 30-second default.
4. Wrap only `send_notification()` in the timeout boundary.
5. On timeout, retain the queue head and return through existing heartbeat and
   token-owned lock cleanup.
6. Run the focused test and coordinator suite to verify GREEN.

### Task 2: Make badge idempotency quiet

**Files:**

- Modify: `bot/tests/infrastructure/test_notification_badge_service.py`
- Modify: `bot/infrastructure/services/notification_badge_service.py`

1. Add a test raising `TelegramBadRequest` with `message is not modified` and
   capture Loguru records.
2. Run the focused test and verify RED because the event is currently logged as
   `notification_badge_edit_failed` at error level.
3. Recognize only that exact Telegram response as a debug no-op.
4. Run the focused test and badge suite to verify GREEN.

### Task 3: Improve coordinator diagnostics

**Files:**

- Modify: `bot/tests/infrastructure/test_notification_coordinator.py`
- Modify: `bot/infrastructure/services/notification_coordinator.py`

1. Assert timeout and lock-contention diagnostics contain user, notification,
   reason, and timing fields in rendered text.
2. Verify RED, then minimally update the relevant messages.
3. Log unsuccessful token-owned lock release as a warning and normal release at
   debug level.
4. Run both infrastructure suites.

### Task 4: Verify and close the task

**Files:**

- Modify/move: `docs/exec-plans/active/2026-07-18-notification-delivery-timeout.md`

1. Run both focused suites.
2. Run `just test` and `just check-fast`.
3. Run `git diff --check` and review the scoped diff.
4. Record verification evidence, check all execution-plan items, and move the
   plan to `docs/exec-plans/completed/`.
