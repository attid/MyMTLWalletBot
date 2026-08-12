# bot-started-commit: Include commit in bot startup notification

## Context

The runtime image already exposes `GIT_COMMIT`, and startup logs include it, but
the Telegram admin notification is hard-coded to `Bot started`. Keep both
startup surfaces consistent and regression-tested.

## Files/Directories To Change

- `bot/start.py`
- `bot/tests/other/test_startup_wiring.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User approved the listed paths with `++`.

## Change Plan

1. [x] Add a failing regression test for the commit-bearing startup message.
2. [x] Add one startup commit/message formatter in `bot/start.py`.
3. [x] Use the formatter for both the admin notification and startup log.
4. [x] Run focused tests and `just check-fast`.
5. [x] Finish the execution plan.

## Risks / Open Questions

- The environment may omit `GIT_COMMIT`; preserve the existing `unknown`
  fallback rather than failing startup.

## Verification

- `uv run pytest bot/tests/other/test_startup_wiring.py -q`
- `just check-fast`
- Expected: startup notification contains the seven-character image commit and
  all checks pass.
