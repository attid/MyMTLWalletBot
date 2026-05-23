# assets-clear-state: Clear assets state like send command

## Context

The `/send` command starts by calling `clear_state(state)`, which removes stale
FSM data while preserving `last_message_id` for tracked menu replacement. The
hidden `/assets` command should use the same pattern so old asset/request/signing
state does not leak into a new `/assets` flow.

## Files/Directories To Change

- `bot/routers/assets.py`
- `bot/tests/routers/test_assets.py`
- `docs/exec-plans/active/2026-05-23-assets-clear-state.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> посмотри как команда /send очищает номер сообщения сделай также в /assets

## Change Plan

1. [x] Call `clear_state(state)` at the beginning of `/assets`, matching
   `/send`.
2. [x] Add router coverage that stale asset request state is removed while
   `last_message_id` is preserved.
3. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- `clear_state` preserves `last_message_id`; this is intentional and matches
  `/send`.

## Verification

- `uv run pytest bot/tests/routers/test_assets.py -q`
  - `6 passed in 2.21s`
- `uv run ruff check bot/routers/assets.py bot/tests/routers/test_assets.py`
  - `All checks passed!`
- `uv run ruff format --check bot/routers/assets.py bot/tests/routers/test_assets.py`
  - `2 files already formatted`
- `just check-fast`
  - `ruff check .`: `All checks passed!`
  - `mypy core`: `Success: no issues found in 28 source files`
  - `pytest tests/core tests/infrastructure tests/other -m "not integration"`:
    `415 passed in 5.86s`
  - `check_import_boundaries.py`: `Import boundary checks passed.`
  - `check_docs_contract.py`: `Docs contract checks passed.`
  - `check_exec_plan_scope_lock.py`: `Execution plan scope-lock checks passed.`
