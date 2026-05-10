# 2026-05-10-refresh-balance-deadlock: Refresh balance deadlock fix

## Context

Production logs show Firebird `deadlock/update conflicts with concurrent update`
while persisting `MYMTLWALLETBOT` balance cache during the `Refresh` callback.
The original flush error is then swallowed by the balance rendering path, so the
router later calls `session.commit()` on a failed SQLAlchemy transaction and
surfaces `PendingRollbackError`.

## Files/Directories To Change

- `bot/core/use_cases/wallet/get_balance.py`
- `bot/infrastructure/persistence/sqlalchemy_wallet_repository.py`
- `bot/core/interfaces/repositories.py`
- `bot/routers/start_msg.py`
- `bot/routers/common_start.py`
- `bot/tests/core/test_get_balance.py`
- `bot/tests/infrastructure/test_infrastructure_repositories.py`
- `bot/tests/routers/test_common_start.py`
- `docs/exec-plans/completed/2026-05-10-2026-05-10-refresh-balance-deadlock.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> Implement the plan.
>
> Prior plan scope selected: Refresh only (Recommended); Wallet paths (Recommended).

## Change Plan

1. [x] Add RED tests for forced refresh, cache-write conflict handling, and refresh router behavior.
2. [x] Add `force_refresh` through `GetWalletBalance.execute`, `cmd_show_balance`, and `get_start_text`.
3. [x] Replace refresh cache reset with forced live balance fetch.
4. [x] Add repository cache-only write API that can skip transient Firebird cache write conflicts.
5. [x] Stop swallowing DB transaction failures in balance rendering.
6. [x] Run focused tests and local validation.

## Risks / Open Questions

- Cache writes are best-effort only for balance cache; non-cache wallet updates must still fail loudly.
- Existing unrelated worktree changes must not be modified.

## Verification

- `uv run pytest bot/tests/core/test_get_balance.py -q`
- `uv run pytest bot/tests/infrastructure/test_infrastructure_repositories.py -q`
- `uv run pytest bot/tests/routers/test_common_start.py -q`
- `just lint`
- `just test-fast`
- `just arch-test`
