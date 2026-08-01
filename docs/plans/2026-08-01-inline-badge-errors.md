# Inline Search and Stale Badge Error Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development
> to implement this plan task-by-task.

**Goal:** Prevent Stellar URI text from overflowing Firebird username search
parameters and treat deleted badge target messages as recoverable stale state.

**Architecture:** Validate inline text at the router before selecting the
username-search path, with a second length guard at the repository boundary.
Handle Telegram's specific `message to edit not found` response inside the
badge service by deleting the stale base-markup key under the existing UI
lease; preserve full exception handling for all unknown failures.

**Tech Stack:** Python 3.12, aiogram, SQLAlchemy, Firebird, Redis, pytest.

---

### Task 1: Bound Inline Username Search

**Files:**

- Modify: `bot/routers/send.py:1195-1265`
- Modify: `bot/infrastructure/persistence/sqlalchemy_user_repository.py:101-109`
- Test: `bot/tests/routers/test_send.py`
- Test: `bot/tests/infrastructure/test_infrastructure_repositories.py`

1. Add a router test proving a Stellar URI does not invoke
   `search_by_username`.
2. Add a repository test proving input longer than the Firebird pattern bound
   returns `[]` without calling `session.execute`.
3. Run both tests and verify RED.
4. Add a username-shape predicate in the router and a repository length guard.
5. Run both focused suites and verify GREEN.

### Task 2: Recover Stale Badge Targets

**Files:**

- Modify: `bot/infrastructure/services/notification_badge_service.py:235-272`
- Test: `bot/tests/infrastructure/test_notification_badge_service.py`

1. Add a test whose bot returns `Bad Request: message to edit not found`.
2. Assert the stored base markup is deleted and no
   `notification_badge_edit_failed` ERROR is emitted.
3. Assert an unrelated Telegram bad request still emits the existing error.
4. Run the tests and verify RED.
5. Handle only the evidenced missing-message response, clear the key through
   the lease-aware Redis operation, and log one compact stale-target record.
6. Run the focused badge suite and verify GREEN.

### Task 3: Verify and Complete

**Files:**

- Update: `docs/exec-plans/active/2026-08-01-inline-badge-errors.md`
- Move to: `docs/exec-plans/completed/2026-08-01-inline-badge-errors.md`

1. Run all three affected test suites.
2. Run `just check-fast`.
3. Run `just test`.
4. Record verification results and complete the execution plan.
