# default-xlm-notification-filter: Default XLM notification filter

## Context

Small XLM payment effects such as `0.0001 XLM` create noisy Telegram
notifications. Every new user should receive a normal, user-deletable
notification filter:

- operation: `payment`
- asset: `XLM`
- min amount: `0.1`
- wallet: all wallets

Existing users need a one-time maintenance backfill. This must not be a
permanent Telegram admin command, and the filter must not be recreated on
`/start` after a user deletes it.

## Files/Directories To Change

- `bot/core/interfaces/repositories.py`
- `bot/core/use_cases/user/register.py`
- `bot/infrastructure/factories/use_case_factory.py`
- `bot/infrastructure/persistence/sqlalchemy_notification_repository.py`
- `bot/scripts/maintenance/`
- `bot/tests/core/`
- `bot/tests/infrastructure/`
- `docs/exec-plans/active/2026-05-28-default-xlm-notification-filter.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add failing repository tests for idempotent default XLM filter creation
       and existing-user backfill.
2. [x] Add failing registration/use-case test proving new users receive the
       default XLM notification filter.
3. [x] Implement repository methods and interface contract.
4. [x] Wire registration to create the default filter only during new-user
       creation.
5. [x] Add a maintenance backfill entry point for one-time existing-user
       population without adding a Telegram command.
6. [x] Run focused tests, then `just check-fast`.

## Risks / Open Questions

- Re-running a broad backfill after users delete the filter would re-create it.
  The maintenance entry point should be treated as one-time deployment work.
- Current filter matching uses `filter.min_amount > amount`; that already
  suppresses dust values like `0.0001` for a `0.1` threshold and does not need
  behavior changes for this task.

## Verification

- Focused repository/use-case tests pass.
- `just check-fast` passes.
