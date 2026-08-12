# Router Test Session Close Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development
> to implement this plan task-by-task.

**Goal:** Remove Aiogram's unnecessary SSL graceful-shutdown delay from local
plain-HTTP router tests.

**Architecture:** Keep Aiogram's `AiohttpSession` for requests, but explicitly
create and retain its underlying aiohttp client session in the `router_bot`
fixture. Close that local client session directly at teardown so production
SSL behavior remains untouched.

**Tech Stack:** pytest, Aiogram, aiohttp.

---

### Task 1: Optimize the test fixture

**Files:**

- Modify: `bot/tests/conftest.py:726-739`

1. Record the baseline router-suite duration and teardown total.
2. Create the aiohttp client session through `AiohttpSession.create_session()`
   before yielding the bot.
3. Close the retained client session directly after the fixture yields.

### Task 2: Verify and complete

**Files:**

- Update: `docs/exec-plans/active/2026-08-12-router-test-session-close.md`
- Move to: `docs/exec-plans/completed/2026-08-12-router-test-session-close.md`

1. Run all router tests and compare duration with the 66.97-second baseline.
2. Run `just check-fast`, `just test`, and `git diff --check`.
3. Record results and complete the execution plan.
