# Bot Pool Hang Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task.

**Goal:** Prevent indefinitely blocked Telegram work from exhausting every DB
connection and make future slow checkouts attributable.

**Architecture:** Keep external I/O outside DB session scopes, retain
warning-only monitoring for retry-safe delivery, and detect Firebird failure
through the existing bounded DB health probe. Preserve existing delivery
semantics and dependency injection.

**Tech Stack:** Python 3.12, asyncio, aiogram middleware, SQLAlchemy async
sessions, pytest.

---

### Task 1: Preserve Telegram update lifetime

**Files:**

- Modify: `bot/middleware/db.py`
- Create: `bot/tests/middleware/test_db.py`

1. Remove the global handler deadline regression tests.
2. Remove handler cancellation while retaining checkout ownership context.
3. Verify existing middleware behavior remains green.

### Task 2: Preserve retry-safe task monitoring

**Files:**

- Modify: `bot/infrastructure/utils/async_utils.py`
- Create: `bot/tests/infrastructure/test_async_utils.py`

1. Write a test whose decorated coroutine exceeds the warning threshold.
2. Verify it fails because the current implementation cancels the coroutine.
3. Restore warning-only monitoring.
4. Verify the coroutine continues and completes after release.

### Task 3: Shorten message-worker DB ownership

**Files:**

- Modify: `bot/infrastructure/workers/message_worker.py`
- Modify: `bot/tests/infrastructure/test_message_worker.py`

1. Write a test recording session depth during outbound message work.
2. Verify it fails because the worker keeps its read session open.
3. Snapshot queue fields, close the read session, then send and persist status
   using separate short sessions.
4. Verify delivery and failure paths commit their status without holding a
   session during external I/O.

### Task 4: Attribute long-lived checkouts

**Files:**

- Modify: `bot/db/db_pool.py`
- Create: `bot/tests/infrastructure/test_db_pool.py`

1. Write a test that records task and Telegram-update ownership for a checkout.
2. Verify it fails because checkout ownership is not tracked.
3. Add checkout timing and ownership metadata.
4. Verify the focused pool tests; retain the bounded real DB health probe.

### Task 5: Keep legitimate long delivery healthy

**Files:**

- Modify: `bot/infrastructure/services/bot_health_service.py`
- Modify: `bot/tests/infrastructure/test_bot_health_service.py`

1. Write a test for a running worker beyond the warning threshold with a
   successful DB probe.
2. Verify it fails because the current report marks the worker stale.
3. Report the worker as `running_long` without failing health.
4. Preserve stale detection when no worker is currently running.

### Task 6: Regression gate

1. Run all focused tests.
2. Run `just check-fast`.
3. Complete and move the execution plan.
