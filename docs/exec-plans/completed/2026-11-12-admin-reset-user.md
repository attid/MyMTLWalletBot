# admin-reset-user: Real user reset for admins, honest /delete_all

## Context

`/delete_all` (`bot/routers/common_start.py`) has been a stub since the Clean
Architecture refactor: the delete call was commented out and the handler only
answers "All was delete, restart please". The command silently does nothing,
which is the same "lies about success" pattern as the free-wallet bug.

The intended implementation (`DeleteUser`) already exists in
`bot/core/use_cases/user/manage_user.py` but is unreachable (not wired in the
factory) and unsafe: it deletes the `MYMTLWALLETBOT_USERS` row without clearing
`NOTIFICATION_FILTERS` and `MYMTLWALLETBOT_MESSAGES`, both of which have FK to
the user row. Every registered user now has a default XLM notification filter,
so on production this would fail mid-way.

Owner asked for a safe way to verify the wallet-provisioning fix on their own
account without `DELETE FROM` (money/keys must not be lost).

Decision (owner): implement admin-only `/reset_user @user_or_id`.

## Files/Directories To Change

- `bot/core/interfaces/repositories.py`
- `bot/infrastructure/persistence/sqlalchemy_message_repository.py`
- `bot/core/use_cases/user/manage_user.py`
- `bot/infrastructure/factories/use_case_factory.py`
- `bot/routers/admin.py`
- `bot/routers/common_start.py`
- `bot/tests/core/test_use_cases_new.py`
- `bot/tests/routers/test_admin.py`
- `bot/tests/routers/test_common_start.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> "ок давай в2" — approval of option 2 (admin-only `/reset_user`) from the
> proposal, which listed `bot/routers/admin.py`, `bot/core/use_cases/user/manage_user.py`,
> `bot/infrastructure/factories/use_case_factory.py`, `bot/tests/**`.

## Change Plan

1. [x] `IMessageRepository.delete_all_by_user()` + implementation.
2. [x] `DeleteUser.execute` cleans dependents in FK-safe order: notification
   filters -> queued messages -> wallets (soft delete, keys stay) -> user row.
   Dependencies become explicit constructor arguments.
3. [x] `IUseCaseFactory.create_delete_user()` + implementation.
4. [x] `/reset_user @username_or_id` admin command (admin router already filters
   by `config.admins`): resolves target, runs the use case, clears
   `last_message_id`, reports what was done and that keys remain in DB.
5. [x] `/delete_all` no longer lies: honest reply that nothing is deleted and
   wallets are created automatically on `/start`; reset is admin-only.
6. [x] Tests: use-case order/rollback-free happy path, admin command (found by id
   and by username, unknown user, bad usage, non-admin is filtered out),
   `/delete_all` reply.
7. [x] Run `just check-fast`, `just test-e2e-smoke`, `just test`.
8. [x] Move plan to completed with `just finish-task`.

## Risks / Open Questions

- Soft delete keeps `secret_key`/`seed_key`/`wallet_crypto_v2` in the DB row with
  `NEED_DELETE=1`; funds on old addresses are not lost, but the bot stops showing
  them. Documented in the command reply.
- `/reset_user` is destructive for the target's bot state (default address,
  filters, queued messages). Restricted to `config.admins` by the router filter.
- Out of scope: restoring soft-deleted wallets back to the bot, purging old
  wallet rows, and any bulk migration of historical data.

## Verification

- `uv run pytest bot/tests/routers/test_admin.py bot/tests/core/test_use_cases_new.py -q`
  -> 36 passed
- `uv run pytest bot/tests/routers/test_common_start.py -q` -> 25 passed
- `just check-fast` -> 657 passed, structural checks passed
- `just test-e2e-smoke` -> 145 passed
- `just test` -> 1079 passed, 8 deselected

## Outcome

- `/reset_user @user_or_id` (admin only, `config.admins` filter on the router):
  deletes notification filters and queued messages, soft-deletes wallets
  (`NEED_DELETE=1`, keys stay), deletes the user row, clears
  `last_message_id`; next `/start` registers and provisions a new wallet.
- `/delete_all` now answers that nothing was deleted (no more fake success).
- `DeleteUser` is wired through `IUseCaseFactory.create_delete_user` and is safe
  with respect to FKs (`NOTIFICATION_FILTERS`, `MYMTLWALLETBOT_MESSAGES`).
