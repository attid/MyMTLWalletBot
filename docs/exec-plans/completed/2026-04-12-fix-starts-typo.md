# fix-starts-typo: Fix STARTS typo to STARS in inout.py

## Context

Typo: button text, callback_data, state and function names used "STARTS" instead of "STARS".

## Files/Directories To Change

- `bot/routers/inout.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> User requested: "опятчу надо поправить STARTS -> STARS"

## Change Plan

1. [x] Rename State `sending_starts_sum_in` → `sending_stars_sum_in`
2. [x] Fix button text and callback_data `STARTS` → `STARS`
3. [x] Rename handler functions `cmd_starts_in` → `cmd_stars_in`, `cmd_send_starts_sum` → `cmd_send_stars_sum`
4. [x] `just check-fast` passes.

## Risks / Open Questions

- None.

## Verification

- `just check-fast`: 356 passed, all linters green.
