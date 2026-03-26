# make-mongodb-url-optional: Make mongodb_url optional

## Context

`mongodb_url` currently breaks config validation when absent and also triggers
Mongo client initialization at import time. The task is to make the setting
optional and ensure no Mongo connection is attempted unless it is actually
configured and used.

## Files/Directories To Change

- `bot/other/config_reader.py`
- `bot/db/mongo.py`
- `bot/tests/other/test_import_sanity.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> +

## Change Plan

1. [x] Add a regression test covering import/config behavior when `mongodb_url` is absent.
2. [x] Make `mongodb_url` optional in `bot/other/config_reader.py`.
3. [x] Remove eager Mongo connection setup from `bot/db/mongo.py` when URL is not configured.
4. [x] Skip docs update because the contract change is internal and covered by tests.
5. [x] Run targeted tests for the changed behavior.

## Risks / Open Questions

- Import-time side effects in unrelated modules can make the regression test noisy.
- `check_account_id_from_grist` should stay safe if Mongo is disabled and return a conservative default.

## Verification

- `uv run pytest bot/tests/other/test_import_sanity.py -q`
- `uv run pytest bot/tests/routers/test_mtltools.py -q`
- Expected signal: import-sanity and affected router tests pass without Mongo import-time failures.
