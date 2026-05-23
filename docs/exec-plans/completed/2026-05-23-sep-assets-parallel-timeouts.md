# sep-assets-parallel-timeouts: Limit SEP discovery latency

## Context

The `/assets` screen still waits too long when several issuers or home domains
have slow SEP discovery endpoints. The list discovery should cap latency more
aggressively and check assets concurrently with a small limit so one dead anchor
does not block the whole wallet scan for minutes.

## Files/Directories To Change

- `bot/infrastructure/services/anchor_discovery_service.py`
- `bot/tests/infrastructure/test_anchor_discovery_service.py`
- `docs/exec-plans/active/2026-05-23-sep-assets-parallel-timeouts.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> не помогло, 3 минуты загрузка висит, давай таймауты более жесткие добавим и паралелльно штуки по 3 проверять.

## Change Plan

1. [x] Add regression coverage that list discovery runs uncached issuer checks
   with at most three concurrent tasks and starts the next check as soon as any
   slot frees.
2. [x] Reduce default discovery HTTP timeout for SEP list/detail requests.
3. [x] Preserve deterministic output order and issuer cache behavior.
4. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Lower timeouts can hide very slow anchors from the first `/assets` list. Users
  can retry after anchor recovery; this is preferable to freezing the wallet UI.

## Verification

- `uv run pytest bot/tests/infrastructure/test_anchor_discovery_service.py -q`
  - `6 passed in 0.36s`
- `uv run ruff check bot/infrastructure/services/anchor_discovery_service.py bot/tests/infrastructure/test_anchor_discovery_service.py`
  - `All checks passed!`
- `just check-fast`
  - `ruff check .`: `All checks passed!`
  - `mypy core`: `Success: no issues found in 27 source files`
  - `pytest tests/core tests/infrastructure tests/other -m "not integration"`:
    `408 passed in 5.38s`
  - `check_import_boundaries.py`: `Import boundary checks passed.`
  - `check_docs_contract.py`: `Docs contract checks passed.`
  - `check_exec_plan_scope_lock.py`: `Execution plan scope-lock checks passed.`
