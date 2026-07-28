# Notification Hot-Path Log Volume Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development
> to implement this plan task-by-task.

**Goal:** Remove per-stage notification success logs while preserving useful
timeout diagnostics.

**Architecture:** Keep the mutable progress snapshot inside each owned flush so
the 90-second timeout can report the last awaited stage. Stop emitting a DEBUG
record on every progress update and before every badge refresh. Render the
timeout context directly in its warning text because the production Loguru text
sink does not include bound extras.

**Tech Stack:** Python 3.12, asyncio, Loguru, pytest.

---

### Task 1: Specify Quiet Success and Actionable Timeout Logging

**Files:**

- Test: `bot/tests/infrastructure/test_notification_coordinator.py`

1. Add a successful-flush test that captures DEBUG records.
2. Assert there are no `notification_flush_stage` or
   `notification_badge_refresh_stage` records.
3. Extend the existing stuck-stage test to assert the rendered timeout message
   contains user, reason, stage, notification ID when present, and timeout.
4. Run the focused tests and verify RED on the success-path log assertions.

### Task 2: Remove Hot-Path Records

**Files:**

- Modify: `bot/infrastructure/services/notification_coordinator.py`

1. Keep `mark_stage()` limited to updating the per-flush progress mapping.
2. Remove the badge-start DEBUG record.
3. Render all timeout fields in `notification_flush_timed_out` warning text.
4. Run the focused tests and verify GREEN.

### Task 3: Verify and Complete

**Files:**

- Update: `docs/exec-plans/active/2026-07-27-notification-log-volume.md`
- Move to: `docs/exec-plans/completed/2026-07-27-notification-log-volume.md`

1. Run the coordinator test file.
2. Run `just check-fast`.
3. Run `just test`.
4. Record results and complete the execution plan.
