# sep-requests-partial-failures: Handle partial SEP request failures

## Context

Ultra Capital returns `403 {"type":"authentication_required"}` from
`/sep6/transactions?asset_code=yXLM` in the current flow. The Requests button
should not fail the whole screen when one protocol endpoint rejects the request,
and logs should include enough response details to diagnose anchor behavior.

## Files/Directories To Change

- `bot/infrastructure/services/anchor_transaction_service.py`
- `bot/tests/infrastructure/test_anchor_transaction_service.py`
- `docs/exec-plans/active/2026-05-23-sep-requests-partial-failures.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ладно давай кнопку добьем не работает  Could not load requests.
> Unexpected JSON response from https://ultracapital.xyz/sep6/transactions?asset_code=yXLM: 403
> в логе пусто

## Change Plan

1. [x] Add explicit SEP request error type with status/body context.
2. [x] Catch per-protocol transaction failures, log them, and continue with
   successful protocol results.
3. [x] Add regression coverage for one protocol failing while another returns
   transactions.
4. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- If both protocol endpoints reject the request, the user will still see no
  requests; logs will now contain the status/body details.

## Verification

- `uv run pytest bot/tests/infrastructure/test_anchor_transaction_service.py -q`
  - `2 passed in 0.45s`
- `uv run ruff check bot/infrastructure/services/anchor_transaction_service.py bot/tests/infrastructure/test_anchor_transaction_service.py`
  - `All checks passed!`
- `just check-fast`
  - `ruff check .`: `All checks passed!`
  - `mypy core`: `Success: no issues found in 28 source files`
  - `pytest tests/core tests/infrastructure tests/other -m "not integration"`:
    `415 passed in 5.19s`
  - `check_import_boundaries.py`: `Import boundary checks passed.`
  - `check_docs_contract.py`: `Docs contract checks passed.`
  - `check_exec_plan_scope_lock.py`: `Execution plan scope-lock checks passed.`
