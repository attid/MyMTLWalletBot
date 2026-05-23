# sep24-asset-transfer: Start SEP-24 asset deposit withdraw

## Context

The hidden SEP asset flow now lists assets and requests. Add only SEP-24
interactive deposit/withdraw start actions: authenticate with SEP-10, call the
SEP-24 interactive endpoint, and show the returned URL as a Telegram button.
SEP-6 deposit/withdraw remains out of scope for this task.

## Files/Directories To Change

- `bot/infrastructure/services/anchor_transaction_service.py`
- `bot/routers/assets.py`
- `bot/keyboards/assets.py`
- `bot/tests/infrastructure/test_anchor_transaction_service.py`
- `bot/tests/routers/test_assets.py`
- `docs/exec-plans/completed/2026-05-23-sep24-asset-transfer.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> да давай пока только сеп 24

## Change Plan

1. [x] Add SEP-24 interactive deposit/withdraw request method to the anchor
   transaction service.
2. [x] Wire Deposit/Withdraw callbacks through the existing PIN/password flow.
3. [x] Show the returned interactive URL as a Telegram URL button plus Return.
4. [x] Add service/router tests.
5. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Read-only/WebApp signing remains out of scope for this step, as with Requests.

## Verification

- `uv run pytest bot/tests/infrastructure/test_anchor_transaction_service.py bot/tests/routers/test_assets.py` - 11 passed.
- `just check-fast` - ruff, mypy core, 416 tests, import boundaries, docs contract, and exec plan scope-lock passed.
