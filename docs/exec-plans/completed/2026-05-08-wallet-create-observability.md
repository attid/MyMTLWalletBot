# wallet-create-observability: Add wallet creation observability

## Context

Successful Stellar wallet creation is currently almost invisible in logs. The
existing flow commits the wallet to DB and subscribes notifications before the
on-chain `create_account` and trustline submissions complete. If a later step
fails, operators cannot tell which step failed or whether the DB-only wallet was
left behind.

## Files/Directories To Change

- `bot/routers/add_wallet.py`
- `bot/infrastructure/services/stellar_service.py` (only if submit metadata is needed)
- `bot/tests/routers/test_add_wallet.py`
- `docs/exec-plans/active/2026-05-08-wallet-create-observability.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add focused router test coverage for creation-step logs.
2. [x] Add structured logs around current `AddWalletNewKey` steps without moving subscribe.
3. [x] Log failure context for the current catch path.
4. [x] Avoid behavior changes unless required for observability.
5. [x] Run focused tests and lint for changed files.

## Risks / Open Questions

- Do not change side-effect ordering unless we can prove compatibility.
- Keep public log fields useful without logging secrets or mnemonics.

## Verification

- `uv run pytest bot/tests/routers/test_add_wallet.py -q`
- `uv run ruff check bot/routers/add_wallet.py bot/tests/routers/test_add_wallet.py`
