# WebApp Notification Completion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task.

**Goal:** Release delayed blockchain notifications when a normal WebApp-signed transaction submits successfully.

**Architecture:** Reuse `complete_notification_flow` at the existing successful terminal boundary in `signing_worker`. Keep failure and sign-only branches unchanged.

**Tech Stack:** Python 3.12, FastStream, fakeredis, pytest, AsyncMock.

---

### Task 1: Add RED worker regressions

**Files:**
- Modify: `bot/tests/test_signing_flow.py`

1. Store a signed transaction and serialized `fsm_after_send` callback in fake
   Redis.
2. Make `submit_signed_xdr` return success.
3. Assert callback ordering is `fsm_after_send`, then `complete_flow`.
4. Add a failed-submit case asserting `complete_flow` is not awaited.
5. Run the focused tests and confirm the success case fails because completion
   is missing.

### Task 2: Complete successful WebApp flows

**Files:**
- Modify: `bot/infrastructure/workers/signing_worker.py`

1. Import `complete_notification_flow` from the notification activity module.
2. Await it after successful optional `fsm_after_send` processing.
3. Run focused tests and confirm GREEN.

### Task 3: Verify and finish

**Files:**
- Modify: `docs/exec-plans/active/2026-07-15-webapp-notification-completion.md`

1. Run `bot/tests/test_signing_flow.py` and relevant notification tests.
2. Run `just check-fast` and `git diff --check`.
3. Mark the execution plan complete and move it to `completed/`.
