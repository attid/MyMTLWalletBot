# wallet-create-retry: Retry Stellar account activation

## Context

Free Stellar wallet creation stores the generated wallet in DB before submitting
the Horizon `create_account` transaction. A transient Horizon/network/sequence
failure after DB commit can leave an unactivated default wallet. Retrying must
rebuild the transaction each time so the source account sequence is freshly
loaded.

## Files/Directories To Change

- `bot/routers/add_wallet.py`
- `bot/infrastructure/services/stellar_service.py` (only if fee/submit API changes are needed)
- `bot/tests/routers/test_add_wallet.py`
- `docs/exec-plans/active/2026-05-08-wallet-create-retry.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add a router/fake-Horizon regression test proving create-account submit is retried 3 times.
2. [x] Extract create-account submit helper in `bot/routers/add_wallet.py`.
3. [x] Rebuild, sign, and submit create-account transaction on every attempt.
4. [x] Preserve existing side-effect order and avoid global fee changes in this patch.
5. [x] Run focused tests and lint for changed files.

## Risks / Open Questions

- Retrying a successful but lost-response create-account can later hit "account already exists"; this patch should not mask unrelated failures unless existence is explicitly confirmed.
- Global fee standardization is separate because `StellarService` hardcodes fees in multiple transaction builders.

## Verification

- `uv run pytest bot/tests/routers/test_add_wallet.py -q`
- `uv run ruff check bot/routers/add_wallet.py bot/tests/routers/test_add_wallet.py`
