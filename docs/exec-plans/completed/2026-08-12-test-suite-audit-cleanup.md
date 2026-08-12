# test-suite-audit-cleanup: Consolidate test fixtures and remove proven duplicate artifacts

## Context

The 900-test suite contains 323 parametrized structural checks, one exact test
body duplicate, one weaker duplicate router scenario, legacy reproduction-test
files, and three router modules that duplicate the shared Telegram bot/session
fixtures. Preserve every unique behavior while removing proven artifacts and
bringing router integration tests back to the documented shared-fixture model.

## Files/Directories To Change

- `bot/tests/conftest.py`
- `bot/tests/README.md`
- `bot/tests/routers/test_common_setting.py`
- `bot/tests/routers/test_inout.py`
- `bot/tests/routers/test_wallet_setting.py`
- `bot/tests/routers/test_wallet_setting_visibility.py`
- `bot/tests/routers/test_send.py`
- `bot/tests/routers/test_uri.py`
- `bot/tests/routers/test_uri_repro.py`
- `bot/tests/routers/test_sign.py`
- `bot/tests/other/test_sign_reproduce.py`
- `bot/tests/other/test_syntax.py`
- `docs/exec-plans/active/2026-08-12-test-suite-audit-cleanup.md`
- `docs/exec-plans/completed/2026-08-12-test-suite-audit-cleanup.md`
- `docs/plans/2026-08-12-test-suite-audit-cleanup.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> After the assistant listed the exact test files and Markdown plan paths, the
> user replied `++`.

## Change Plan

1. [x] Record the collected nodeids and audit evidence before refactoring.
2. [x] Make `RouterTestMiddleware` support the shared injected session and
       migrate the three legacy router modules to `router_bot`,
       `router_app_context`, and common helpers.
3. [x] Merge unique wallet-visibility, URI reproduction, and signing
       reproduction scenarios into their canonical router test modules.
4. [x] Remove only the exact send duplicate, weaker visibility duplicate, and
       redundant syntax sweep.
5. [x] Update test documentation to match the shared session teardown.
6. [x] Verify expected collection changes, targeted suites, `just check`, and
       absence of duplicate test bodies.
7. [x] Move the completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- Fixture consolidation can accidentally change injected DB mock behavior;
  commit/execute assertions must remain explicit.
- Reproduction tests must move without weakening their original assertions.
- Parametrized import-sanity checks remain because their per-module failure IDs
  are useful and they catch import-time runtime errors.

## Verification

- `uv run --package mmwb-bot pytest tests/routers/test_common_setting.py tests/routers/test_inout.py tests/routers/test_wallet_setting.py tests/routers/test_send.py tests/routers/test_uri.py tests/routers/test_sign.py -q`
- `uv run --package mmwb-bot pytest tests --collect-only -q`
- `just check`
- `git diff --check`
- Expected collection count: 696 selected tests, with only the 202 syntax
  parameter cases and two proven duplicate behaviors removed from the previous
  900-test baseline.
- Actual collection: 696 selected, 7 external tests deselected.
- Changed router contour: 70 passed in 4.97 seconds.
- Full suite: 696 passed, 7 deselected in 25.64 seconds.
- `just lint`: Ruff and mypy passed.
- `just arch-test`: import boundaries, docs contract, and execution-plan scope
  checks passed.
- AST audit: zero exact duplicate test-function bodies.
- Local router/other fixture audit: no private `bot`, `mock_session`, or
  `mock_app_context` fixture definitions remain.
