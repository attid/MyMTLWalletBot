# e2e-wallet-lifecycle: E2E harness: app context on sqlite + testnet, wallet lifecycle smoke

## Context

The nightly canary (`tests/external/test_testnet_canary.py`) exercises only
stellar-sdk and friendbot: it never boots the bot. Free-wallet creation was
broken for months and no check noticed. This slice introduces an end-to-end
harness that builds the real application objects (StellarService, repositories,
repositories, aiogram dispatcher) against the Stellar testnet and sqlite, and
covers the first and most important route: creating a free wallet.

## Files/Directories To Change

- `bot/tests/e2e/__init__.py` (new)
- `bot/tests/e2e/conftest.py` (new)
- `bot/tests/e2e/test_wallet_lifecycle.py` (new)
- `bot/tests/e2e/README.md` (new)
- `bot/start.py`
- `bot/other/config_reader.py`
- `.env.template`
- `docs/exec-plans/active/2026-11-14-e2e-wallet-lifecycle.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add `DISABLE_WORKERS` / `DISABLE_SCHEDULER` switches (default = current
   production behaviour).
2. [x] Add the E2E fixtures: sqlite pool with the `DatabasePool` session
   contract, testnet `StellarService`, friendbot-funded master wallet and test
   issuer asset, real `AppContext`.
3. [x] Cover free-wallet creation end to end: DB row, on-chain account,
   trustline.
4. [x] Document how to run the harness.
5. [x] Run `just check-fast` and `just check`.

## Risks / Open Questions

- The harness needs internet and friendbot; it is marked `external` and stays
  out of the default `pytest` run.
- `FREE_WALLET_ASSETS` are mainnet issuers, so the harness swaps them for a
  testnet asset instead of pretending mainnet trustlines work.
- Still uncovered: send, order, swap, receive.

## Outcome (2026-11-14)

- `tests/e2e` boots a real `AppContext` on sqlite with the testnet
  `StellarService` (testnet passphrase) and `mock_telegram` as the Telegram API.
- Master wallet (`user_id=0`) and the issuer of a testnet asset are created on
  the fly via friendbot; `FREE_WALLET_ASSETS` is patched for the run.
- `test_free_wallet_is_created_in_db_and_on_testnet` presses "create wallet" and
  asserts the sqlite row (free, default, crypto container), the testnet account
  and its trustline.

## Verification

- `cd bot && HORIZON_URLS=... uv run --package mmwb-bot pytest tests/e2e -m external -v` -> 1 passed (~19 s)
- `just check-fast`
- `just check`
