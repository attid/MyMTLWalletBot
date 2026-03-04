# refresh-cache-invalidation: Refresh cache invalidation hotfix

## Context

User reported that pressing `Refresh` shows "Nothing to update" while stale wallet
data is still displayed. Root cause was traced to cache invalidation resetting only
`balances_event_id` while leaving cached `balances` payload intact.

## Files/Directories To Change

- `bot/infrastructure/persistence/sqlalchemy_wallet_repository.py`
- `bot/tests/infrastructure/test_infrastructure_repositories.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "+"

## Change Plan

1. [x] Add failing regression test for `reset_balance_cache` in
   `test_infrastructure_repositories.py` to prove stale balance cache behavior.
2. [x] Implement minimal fix in `SqlAlchemyWalletRepository.reset_balance_cache`:
   clear `wallet.balances` and keep event id marker reset.
3. [x] Re-run targeted tests for repository regression and Refresh router behavior.
4. [x] Update execution docs for AI-first compliance.
5. [x] Record exact verification commands and outputs.

## Risks / Open Questions

- Full `just check` was not executed in this fix cycle; only targeted tests were
  executed to validate bugfix behavior.
- Existing `SET_ACTIVE` flow depends on FSM wallet mapping shape; not changed in this
  hotfix.

## Verification

- `uv run pytest tests/infrastructure/test_infrastructure_repositories.py::test_wallet_repository_reset_balance_cache_clears_cached_balances -q`
  - red before fix: failed on `assert refreshed_wallet.balances is None`
  - green after fix: `1 passed`
- `uv run pytest tests/routers/test_common_start.py::test_cmd_refresh_balances -q`
  - green: `1 passed`
