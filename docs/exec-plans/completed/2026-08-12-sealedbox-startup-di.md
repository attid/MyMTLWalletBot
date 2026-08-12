# sealedbox-startup-di: Fix sealed-box startup dependency injection

## Context

The sealed-box release crashes during startup because its service dependency was
passed to `NotificationService` instead of `AppContext`. Existing tests import
the startup module but do not validate constructor wiring inside `main()`.

## Files/Directories To Change

- `bot/start.py`
- `bot/tests/`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> `++`

## Change Plan

1. [x] Add a regression test validating startup constructor keyword wiring.
2. [x] Inject the sealed-box service into `AppContext` instead of
   `NotificationService`.
3. [x] Run focused startup regression tests.
4. [x] Run repository lint, tests, and architecture checks.

## Risks / Open Questions

- Startup tests must catch real constructor signature mismatches without
  executing external Telegram, Redis, database, or scheduler services.

## Verification

- Focused startup wiring test reproduces the failure before the fix and passes
  after it.
- `just lint`, `just test`, and `just arch-test` pass.

Final results:

- Startup regression: 2 passed.
- `just lint`: passed.
- `just test`: 732 passed, 7 deselected.
- `just arch-test`: passed.
