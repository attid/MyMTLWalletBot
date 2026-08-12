# Test Suite Audit Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development
> to implement this plan task-by-task.

**Goal:** Consolidate shared router fixtures and remove only test cases proven
to be redundant while preserving every unique behavior.

**Architecture:** Keep Telegram, application context, and database-session test
infrastructure in `tests/conftest.py`. Feature modules retain only setup that is
specific to their router. Regression scenarios live beside the canonical
router tests instead of in ad-hoc reproduction files.

**Tech Stack:** pytest, pytest-asyncio, Aiogram, aiohttp.

---

### Task 1: Consolidate router infrastructure

**Files:**

- Modify: `bot/tests/conftest.py`
- Modify: `bot/tests/routers/test_common_setting.py`
- Modify: `bot/tests/routers/test_inout.py`
- Modify: `bot/tests/routers/test_wallet_setting.py`

1. Preserve the existing router tests as the RED safety net.
2. Allow `RouterTestMiddleware` to inject the common `mock_session`.
3. Replace local bot, session, middleware, and update constructors with shared
   fixtures/helpers.
4. Run the three migrated modules after each conversion.

### Task 2: Merge ad-hoc regression modules

**Files:**

- Modify: `bot/tests/routers/test_wallet_setting.py`
- Delete: `bot/tests/routers/test_wallet_setting_visibility.py`
- Modify: `bot/tests/routers/test_uri.py`
- Delete: `bot/tests/routers/test_uri_repro.py`
- Modify: `bot/tests/routers/test_sign.py`
- Delete: `bot/tests/other/test_sign_reproduce.py`

1. Move unique error-path assertions to the canonical router modules.
2. Use `mock_telegram` transitively through `router_app_context`.
3. Delete the weaker duplicate visibility scenario and obsolete source files.
4. Run each canonical router module.

### Task 3: Remove proven structural duplication

**Files:**

- Modify: `bot/tests/routers/test_send.py`
- Delete: `bot/tests/other/test_syntax.py`
- Modify: `bot/tests/README.md`

1. Remove one of the two byte-for-byte-equivalent keyboard tests.
2. Remove the syntax sweep, whose checks are covered by Ruff, pytest
   collection, and production-module import sanity.
3. Correct the documented `router_bot` teardown pattern.

### Task 4: Verify collection and behavior

**Files:**

- Update: `docs/exec-plans/active/2026-08-12-test-suite-audit-cleanup.md`
- Move to: `docs/exec-plans/completed/2026-08-12-test-suite-audit-cleanup.md`

1. Confirm the collected count changes from 900 to 696 for the expected
   reasons only.
2. Re-run the AST exact-duplicate audit.
3. Run `just check` and `git diff --check`.
4. Record evidence and complete the execution plan.
