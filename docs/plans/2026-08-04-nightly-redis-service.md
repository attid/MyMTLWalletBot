# Nightly Redis Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development
> to implement this plan task-by-task.

**Goal:** Start a disposable Redis instance before the scheduled external
integration tests run.

**Architecture:** Define Redis as a GitHub Actions job service so the existing
`REDIS_URL=redis://localhost:6379/0` resolves to a real dependency. Use the
container healthcheck to prevent pytest from racing Redis startup; keep the
real integration tests strict rather than converting infrastructure failure
into a skip.

**Tech Stack:** GitHub Actions, Redis 7 Alpine, pytest.

---

### Task 1: Add the Redis job service

**Files:**

- Modify: `.github/workflows/external-integration.yml`

1. Run a structural assertion that requires `jobs.external-tests.services.redis`
   and verify it fails because the service is absent.
2. Add `redis:7-alpine`, expose port 6379, and configure a bounded
   `redis-cli ping` healthcheck.
3. Run the same structural assertion and verify it passes.

### Task 2: Document and verify

**Files:**

- Modify: `bot/tests/external/README.md`
- Update: `docs/exec-plans/active/2026-08-04-nightly-redis-service.md`
- Move to: `docs/exec-plans/completed/2026-08-04-nightly-redis-service.md`

1. Add Redis to the external-suite requirements and identify the two real
   Redis parity tests.
2. Run `just check-fast` and `git diff --check`.
3. Record results and complete the execution plan.
