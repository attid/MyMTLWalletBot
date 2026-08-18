# Notification Lock Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task.

**Goal:** Prevent a stuck Firebird cancellation from renewing a notification lock forever or blocking Telegram flow completion.

**Architecture:** Bound the independent Redis heartbeat with its own monotonic deadline. Convert `complete_flow` into a generation-fenced durable handoff, and isolate per-user delivery tasks in the polling worker.

**Tech Stack:** Python 3.12, asyncio, Redis/fakeredis, pytest, aiogram.

---

### Task 1: Bound heartbeat renewal independently

**Files:**
- Modify: `bot/tests/infrastructure/test_notification_coordinator.py`
- Modify: `bot/infrastructure/services/notification_coordinator.py`

1. Add a test whose sender suppresses cancellation and remains blocked after the
   ownership timeout.
2. Run the test and verify renewals continue with the current implementation.
3. Pass a monotonic deadline to `_heartbeat_lock` and stop renewing once reached.
4. Run the focused test and verify renewal count becomes stable while the sender
   remains blocked.

### Task 2: Hand completed flows to the durable worker

**Files:**
- Modify: `bot/tests/infrastructure/test_notification_coordinator.py`
- Modify: `bot/infrastructure/services/notification_coordinator.py`

1. Replace immediate-flush expectations with a test asserting generation-safe
   hold release and no lock acquisition or sender call.
2. Run the test and verify the old synchronous flush fails it.
3. Give every touch a monotonic Redis generation and release with
   `release_hold_generation_if_unchanged(..., now=...)` so same-second touches
   cannot be deleted by an older completion.
4. Remove lock acquisition and inline `_flush_with_owned_lock` from
   `complete_flow`; schedule pending work due immediately.
5. Run coordinator and Redis-store tests and verify they pass.

### Task 3: Preserve end-to-end worker delivery

**Files:**
- Modify: `bot/tests/infrastructure/test_notification_webhook.py`

1. Update the active-hold integration test to assert no Telegram send directly
   after `complete_flow`.
2. Invoke the delivery worker and assert the existing keyboard/message-id
   delivery contract.
3. Add a worker regression proving a cancellation-resistant user does not block
   another user or a later poll; bound tracked tasks by batch size.
4. Run webhook and delivery-worker tests.

### Task 4: Preserve late-success acknowledgement

**Files:**
- Modify: `bot/tests/infrastructure/test_notification_coordinator.py`
- Modify: `bot/infrastructure/services/notification_coordinator.py`

1. Model a send that succeeds after heartbeat renewal stops while the original
   Redis token is still valid.
2. Attempt fenced acknowledgement with the original token before acquiring a
   recovery token.
3. Verify the sent queue head is removed exactly once.

### Task 5: Fence concurrent Telegram updates

**Files:**
- Modify: `bot/middleware/notification_activity.py`
- Modify: `bot/infrastructure/services/notification_coordinator.py`
- Modify: `bot/infrastructure/services/notification_redis_store.py`
- Modify: `bot/infrastructure/workers/signing_worker.py`
- Modify: `bot/infrastructure/workers/sealedbox_worker.py`
- Modify: `bot/other/faststream_tools.py`

1. Return deadline and generation atomically from the Redis touch operation.
2. Capture the current generation at Telegram update entry, replace it on touch,
   and reset the task-local fence in middleware cleanup.
3. Make Telegram completion release only its captured generation with no latest
   generation fallback.
4. Route background signing, sealed-box, and WalletConnect completion through an
   explicitly named current-flow API matching their current-FSM semantics.
5. Prove with two concurrent asyncio tasks that an older update cannot release a
   generation touched by a newer update before the older handler completes.

### Task 6: Verify and close

1. Run `just check-fast`.
2. Review `git diff --check` and the execution-plan scope guard.
3. Mark the execution plan complete and move it to `docs/exec-plans/completed/`.
