# Delayed Blockchain Notifications Implementation Plan

> **For Codex:** REQUIRED SUB-SKILLS: use
> `superpowers:test-driven-development` for every behavior change and
> `superpowers:subagent-driven-development` for implementation and review.

**Goal:** Deliver blockchain notifications after a sliding inactivity window
without changing the active FSM screen or `last_message_id`.

**Architecture:** Redis stores absolute holds, ordered per-user Lists,
idempotency Sets, a due Sorted Set, token-owned locks, and base UI markups. A
coordinator owns touch/accept/flush/complete behavior; an aiogram middleware
records activity, a polling worker flushes expired users, and a Telegram adapter
keeps independent notification sends separate from UI rendering.

**Tech Stack:** Python 3.12, aiogram, redis-py asyncio, fakeredis, pytest,
Loguru, Lua scripts, existing `mock_telegram` fixtures.

---

### Task 1: Notification contracts and Redis store

**Files:**

- Create: `bot/core/models/blockchain_notification.py`
- Create: `bot/infrastructure/services/notification_redis_store.py`
- Create: `bot/tests/infrastructure/test_notification_redis_store.py`

1. Write failing tests for hold creation/extension/release, atomic enqueue,
   duplicate rejection, queue order, due rescheduling, exact-head acknowledgement,
   and token-safe lock release.
2. Run the focused tests and confirm failures are caused by missing behavior.
3. Add the serializable notification contract and minimal Redis implementation.
4. Run the focused tests to green and refactor without adding behavior.

### Task 2: Independent Telegram delivery and coordinator

**Files:**

- Create: `bot/infrastructure/services/telegram_delivery_service.py`
- Create: `bot/infrastructure/services/notification_coordinator.py`
- Modify: `bot/infrastructure/services/app_context.py`
- Create: `bot/tests/infrastructure/test_notification_coordinator.py`
- Modify: `bot/tests/infrastructure/test_telegram_utils.py`

1. Write failing tests for immediate accept, queued accept, held flush,
   `ignore_hold`, complete flow, ordered partial acknowledgement, Telegram
   failure retention, and unchanged FSM/`last_message_id`.
2. Confirm RED with focused pytest commands.
3. Implement the separate notification sender and coordinator using Task 1.
4. Confirm GREEN and run existing Telegram utility regressions.

### Task 3: Durable expiry worker and lifecycle

**Files:**

- Create: `bot/infrastructure/workers/notification_delivery_worker.py`
- Modify: `bot/start.py`
- Modify: `bot/other/config_reader.py`
- Create: `bot/tests/infrastructure/test_notification_delivery_worker.py`

1. Write failing tests for expired delivery, renewed hold during worker claim,
   two-worker exclusion, restart recovery with the same Redis instance, and
   clean cancellation.
2. Confirm RED, implement a bounded polling loop without per-user tasks, and
   wire startup/shutdown plus `NOTIFICATION_HOLD_SECONDS` defaulting to 120.
3. Confirm GREEN and ensure worker exceptions are logged without killing the
   loop.

### Task 4: Base keyboard storage and badge behavior

**Files:**

- Modify: `bot/infrastructure/utils/telegram_utils.py`
- Create: `bot/infrastructure/services/notification_badge_service.py`
- Create: `bot/routers/pending_notifications.py`
- Modify: `bot/start.py`
- Create: `bot/tests/infrastructure/test_notification_badge_service.py`
- Create: `bot/tests/routers/test_pending_notifications.py`

1. Write failing tests proving the base keyboard excludes the derived badge,
   repeated refresh never duplicates it, count text is correct, restore works,
   failed edit is non-fatal, and badge click preserves FSM/`last_message_id`.
2. Confirm RED, then implement base-markup capture, derived markup editing, and
   the `notification_pending:flush` callback using `mock_telegram` in router
   tests.
3. Confirm GREEN and run existing Telegram/start-screen tests.

### Task 5: Activity middleware and flow completion

**Files:**

- Create: `bot/middleware/notification_activity.py`
- Modify: `bot/start.py`
- Modify: relevant terminal handlers under `bot/routers/`, limited to send,
  trade/order, signing, settings, `/start`, `Return`, and `DeleteReturn` flows
- Create: `bot/tests/middleware/test_notification_activity.py`
- Modify: matching `bot/tests/routers/test_*.py` files using `mock_telegram`

1. Write failing middleware tests for flow callbacks, active-FSM messages, and
   exclusions for badge, `/start`, Return/DeleteReturn, and terminal callbacks.
2. Write failing router tests showing back/start and successful send/order/
   settings endpoints invoke immediate completion while retryable validation
   errors do not.
3. Confirm RED, implement the middleware and minimal explicit completion hooks,
   then confirm GREEN.

### Task 6: Migrate blockchain notification ingestion

**Files:**

- Modify: `bot/infrastructure/services/notification_service.py`
- Modify: `bot/tests/infrastructure/test_notification_webhook.py`
- Modify: `bot/infrastructure/services/notification_history_service.py` only if
  delivered-history recording must move behind successful flush

1. Write failing webhook tests proving active holds enqueue without Telegram,
   inactive holds deliver independently, stable blockchain events deduplicate,
   and delivery never changes FSM or `last_message_id`.
2. Confirm RED, route filtered blockchain events through the coordinator, remove
   notification-specific `last_message_id` resets, and leave signed-transaction
   result screens unchanged.
3. Confirm GREEN and run notification settings/history/external notifier tests.

### Task 7: Final verification and documentation

**Files:**

- Modify: `docs/architecture.md`
- Modify: `docs/glossary.md`
- Modify: `docs/exec-plans/active/2026-07-11-delayed-blockchain-notifications.md`

1. Run formatting for touched code.
2. Run focused notification, middleware, and router suites.
3. Run `just check-fast` and `just secret-scan`.
4. Review the full diff for secrets, unrelated edits, FSM coupling, and
   transaction-result regressions.
5. Complete documentation and move the execution plan with `just finish-task`.

