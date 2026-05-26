# wallet-default-duplicates: Fix duplicate default wallet handling

## Context

Production error shows `MultipleResultsFound` in
`SqlAlchemyWalletRepository.get_default_wallet()` after adding a read-only
wallet. The likely root cause is multiple active rows for the same user being
marked `default_wallet=1`, possibly because `set_default_wallet()` updates all
active rows with the same public key. The same flow then masks the original
error with `KeyError: 'msg'` in `routers/add_wallet.py`.

## Files/Directories To Change

- `bot/infrastructure/persistence/sqlalchemy_wallet_repository.py`
- `bot/core/use_cases/wallet/add_wallet.py`
- `bot/routers/add_wallet.py`
- `bot/tests/infrastructure/test_infrastructure_repositories.py`
- `bot/tests/routers/test_add_wallet.py`
- `docs/exec-plans/active/2026-05-26-wallet-default-duplicates.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add RED repository test proving `set_default_wallet()` leaves exactly one
   active default when duplicate public keys exist.
2. [x] Add RED router/unit test or targeted assertion for add-wallet error path
   without `msg` in FSM data.
3. [x] Fix repository default selection/update behavior.
4. [x] Fix add-wallet error handlers to avoid `KeyError: 'msg'`.
5. [x] Run focused tests, `git diff --check`, and `just check-fast`.

## Risks / Open Questions

- Existing duplicate rows in production still need a one-time cleanup query.
- Firebird SQL support may limit `ORDER BY/LIMIT` in update statements; keep
  the repository implementation portable.

## Verification

- `uv run pytest bot/tests/infrastructure/test_infrastructure_repositories.py bot/tests/routers/test_add_wallet.py`
- `git diff --check`
- `just check-fast`
