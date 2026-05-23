# sep-asset-requests: Show SEP asset transaction requests

## Context

The hidden SEP asset flow has a Requests button but it only shows a placeholder.
SEP-6 and SEP-24 expose transaction history through `GET /transactions`, usually
authenticated with SEP-10. Implement the first working version using the existing
PIN/password confirmation flow for wallets whose key can be decrypted locally.

## Files/Directories To Change

- `bot/core/models/anchor_transaction.py`
- `bot/infrastructure/services/anchor_transaction_service.py`
- `bot/routers/assets.py`
- `bot/tests/infrastructure/test_anchor_transaction_service.py`
- `bot/tests/routers/test_assets.py`
- `docs/exec-plans/active/2026-05-23-sep-asset-requests.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add normalized anchor transaction models.
2. [x] Add SEP transaction service with SEP-10 auth and SEP-6/24
   `/transactions` calls.
3. [x] Wire Requests button through existing PIN/password flow.
4. [x] Add unit/router tests.
5. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Read-only/WebApp wallets need a continuation after WebApp signs the SEP-10
  challenge. This first step reports that as unsupported instead of silently
  failing.

## Verification

- `uv run pytest bot/tests/infrastructure/test_anchor_transaction_service.py bot/tests/routers/test_assets.py -q`
  - `7 passed in 2.14s`
- `uv run ruff check bot/core/models/anchor_transaction.py bot/infrastructure/services/anchor_transaction_service.py bot/routers/assets.py bot/tests/infrastructure/test_anchor_transaction_service.py bot/tests/routers/test_assets.py`
  - `All checks passed!`
- `uv run ruff format --check bot/core/models/anchor_transaction.py bot/infrastructure/services/anchor_transaction_service.py bot/routers/assets.py bot/tests/infrastructure/test_anchor_transaction_service.py bot/tests/routers/test_assets.py`
  - `5 files already formatted`
- `just check-fast`
  - `ruff check .`: `All checks passed!`
  - `mypy core`: `Success: no issues found in 28 source files`
  - `pytest tests/core tests/infrastructure tests/other -m "not integration"`:
    `414 passed in 5.39s`
  - `check_import_boundaries.py`: `Import boundary checks passed.`
  - `check_docs_contract.py`: `Docs contract checks passed.`
  - `check_exec_plan_scope_lock.py`: `Execution plan scope-lock checks passed.`
