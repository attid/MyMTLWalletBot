# clean-stellar-notfound-logs: Clean Stellar NotFound handling in MTL tools

## Context

MTL tools call `stellar_get_data()`, which loads the user's Stellar account from
Horizon. When the default wallet exists in DB but the on-chain account is
missing or not activated, Horizon returns 404 and `stellar_sdk.exceptions.NotFoundError`
escapes through aiogram. The current generic DB session and Sentry error logging
then emit large duplicate tracebacks and full Telegram update reprs.

## Files/Directories To Change

- `bot/routers/mtltools.py`
- `bot/db/db_pool.py`
- `bot/middleware/sentry_error_handler.py`
- `bot/tests/routers/test_mtltools.py`
- `docs/exec-plans/active/2026-05-08-clean-stellar-notfound-logs.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add a router regression test for MTL tools handling Stellar `NotFoundError`.
2. [x] Handle missing/not-activated Stellar accounts in `bot/routers/mtltools.py`.
3. [x] Stop `bot/db/db_pool.py` from logging non-DB handler exceptions as session errors.
4. [x] Shorten `bot/middleware/sentry_error_handler.py` update logging to a compact summary.
5. [x] Run focused tests and available checks.

## Risks / Open Questions

- Need to avoid hiding real DB rollback failures.
- Need to keep unexpected exceptions visible to the global error handler/Sentry.

## Verification

- `uv run pytest bot/tests/routers/test_mtltools.py -q`
- `uv run ruff check bot/routers/mtltools.py bot/db/db_pool.py bot/middleware/sentry_error_handler.py bot/tests/routers/test_mtltools.py`
