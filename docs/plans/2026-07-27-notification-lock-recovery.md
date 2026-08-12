# Notification Lock Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development
> to implement this plan task-by-task.

**Goal:** Prevent a blockchain-notification flush from retaining its per-user
lock forever and complete successful WalletConnect notification flows.

**Architecture:** Keep the Redis queue as the at-least-once source of truth.
Apply a finite budget only to notification lock ownership, acknowledge messages
under that lock, and perform bounded best-effort badge refresh after release.

**Tech Stack:** Python 3.12, asyncio, aiogram, Redis, pytest.

---

### Task 1: WalletConnect Terminal Completion

**Files:**

- Modify: `bot/tests/test_signing_flow.py`
- Modify: `bot/other/faststream_tools.py`

1. Add a test that runs `do_wc_sign_and_respond()` through its successful
   `stellar_signAndSubmitXDR` path with injected external boundaries.
2. Assert the success screen is sent before
   `notification_coordinator.complete_flow(user_id)`.
3. Run the test and verify it fails because completion is absent.
4. Call the existing `complete_notification_flow()` helper after the success
   render.
5. Run the focused test and verify it passes.

### Task 2: Finite Delivery-Lock Ownership

**Files:**

- Modify: `bot/tests/infrastructure/test_notification_coordinator.py`
- Modify: `bot/infrastructure/services/notification_coordinator.py`

1. Add constructor validation tests for a finite positive lock-lifetime budget.
2. Add a test with a stuck store/sender stage and a short budget.
3. Verify RED: the flush does not return or the new constructor contract is
   missing.
4. Bound `_flush_owned()` inside `_flush_with_owned_lock()` while preserving its
   existing `finally` heartbeat cancellation and token-checked release.
5. Log the timeout with user and reason.
6. Verify GREEN and confirm an unacknowledged item remains unacknowledged.

### Task 3: Badge Outside the Delivery Lock

**Files:**

- Modify: `bot/tests/infrastructure/test_notification_coordinator.py`
- Modify: `bot/infrastructure/services/notification_coordinator.py`

1. Add a test whose badge refresher never returns.
2. Assert delivery is acknowledged and the token-owned delivery lock is released
   before the badge await is allowed to continue.
3. Verify RED under the current in-lock refresh behavior.
4. Return whether `_flush_owned()` changed queue state, release the lock, and
   perform one bounded best-effort badge refresh afterwards.
5. Add structured stage logs and verify GREEN.

### Task 4: Verification and Plan Lifecycle

**Files:**

- Update: `docs/exec-plans/active/2026-07-27-notification-lock-recovery.md`
- Move to: `docs/exec-plans/completed/2026-07-27-notification-lock-recovery.md`

1. Run both focused test files.
2. Run `just check-fast`.
3. Run `just test`.
4. Mark completed checklist items and move the execution plan with
   `just finish-task`.
5. Commit only when explicitly requested by the user.
