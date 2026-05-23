# sep-assets-info-cache: Cache SEP info during asset list discovery

## Context

The `/assets` list needs to avoid false positives for anchors that expose a
SEP endpoint but support only one of several assets from the same issuer. Restore
SEP-6/SEP-24 `/info` checks for list discovery, keep short timeouts, and cache
each endpoint info response so one `TRANSFER_SERVER` is not fetched repeatedly
for every trustline.

## Files/Directories To Change

- `bot/infrastructure/services/anchor_discovery_service.py`
- `bot/tests/infrastructure/test_anchor_discovery_service.py`
- `docs/exec-plans/active/2026-05-23-sep-assets-info-cache.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ладно надо вернуть /sep6/info / /sep24/info но с таймаутом и не запрашивать один и тот же /sep6/info / /sep24/info 5 раз подрят. а то у меня 6 ассетов с одним томл но там только у одного есть sep6

## Change Plan

1. [x] Add endpoint-level SEP info cache with TTL and per-endpoint locks.
2. [x] Make list summary use cached `/info` to filter per-asset support.
3. [x] Keep existing bounded concurrency and timeouts.
4. [x] Update tests for no false positives and no repeated `/info` fetches.
5. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Some slow anchors may be hidden from the list because `/info` now participates
  in list filtering again and is timeout-bounded.

## Verification

- `uv run pytest bot/tests/infrastructure/test_anchor_discovery_service.py -q`
  - `6 passed in 0.39s`
- `uv run ruff check bot/infrastructure/services/anchor_discovery_service.py bot/tests/infrastructure/test_anchor_discovery_service.py`
  - `All checks passed!`
- `uv run ruff format --check bot/infrastructure/services/anchor_discovery_service.py bot/tests/infrastructure/test_anchor_discovery_service.py`
  - `2 files already formatted`
- `just check-fast`
  - `ruff check .`: `All checks passed!`
  - `mypy core`: `Success: no issues found in 27 source files`
  - `pytest tests/core tests/infrastructure tests/other -m "not integration"`:
    `408 passed in 5.12s`
  - `check_import_boundaries.py`: `Import boundary checks passed.`
  - `check_docs_contract.py`: `Docs contract checks passed.`
  - `check_exec_plan_scope_lock.py`: `Execution plan scope-lock checks passed.`
