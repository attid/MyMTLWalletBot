# free-wallet-provisioning: Provision free wallet on registration

## Context

Since the registration refactor (`d6fce44` + `a4ea191`, 2026-01-17) `/start`
creates the free wallet row in DB but never activates the Stellar account:

- `RegisterUser` inserts a wallet with `is_free=1, default_wallet=1`;
- `cmd_show_balance` new-user detection changed from `db_is_new_user()` (no user
  OR no wallet) to `if not user:`, so the old `AddNew` -> `AddWalletNewKey`
  provisioning path is no longer reachable for new users.

`create_account`, trustlines and notifier subscription live only in
`cq_add_new_key`, therefore new users end up with DB-only wallets that do not
exist on-chain (Horizon 404). Nothing is logged because no network call is made,
and `GetWalletBalance` silently returns `[]` for a missing account.

Historical 8 dead wallets are explicitly out of scope (owner decision).

## Files/Directories To Change

- `bot/infrastructure/services/free_wallet_provisioning.py` (new)
- `bot/routers/add_wallet.py`
- `bot/routers/common_start.py`
- `bot/langs/en.json`, `bot/langs/ru.json`, `bot/langs/ua.json`,
  `bot/langs/me.json`, `bot/langs/am.json`, `bot/langs/hy.json`
- `bot/tests/infrastructure/test_free_wallet_provisioning.py` (new)
- `bot/tests/routers/test_common_start.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++" (confirmation of the allowed paths and defaults stated in the task
> message: provisioning service, add_wallet, common_start, langs, tests;
> no backfill for the 8 existing dead wallets).

## Change Plan

1. [x] Add `bot/infrastructure/services/free_wallet_provisioning.py`:
   - `WalletProvisioningError(step, cause)`;
   - `ensure_provisioned(*, stellar_service, encryption_service,
     wallet_repository, notification_service, user_id, public_key, secret_key,
     check_account=True)`;
   - move `_submit_create_account_with_retries` here keeping the existing log
     keys `wallet_stellar_account_create_attempt`,
     `wallet_stellar_account_created`,
     `wallet_stellar_account_create_attempt_failed`;
   - create 4 trustlines (MTL/EURMTL/SATSMTL/USDM) and `subscribe`;
   - structured logs `wallet_provision_start|account_exists|completed|failed`;
   - notifier subscribe is best-effort (its failure must not leave a DB-only
     wallet).
2. [x] `bot/routers/add_wallet.py`: replace inline provisioning with
   `ensure_provisioned(check_account=False)`; keep `new_wallet_lock`, existing
   step logs and the outer `wallet_create_failed` handler (include
   `getattr(e, "step", create_step)`).
3. [x] `bot/routers/common_start.py`:
   - new user: after `commit` run `ensure_provisioned(check_account=True)` under
     `new_wallet_lock`; log `wallet_registration_start` and
     `wallet_registration_provisioning_failed` (plus admin alert); on failure
     show `wallet_create_error` and continue to language selection;
   - existing user: best-effort retry for free wallets whose on-chain account is
     missing (this is the retry path after a failed first attempt).
4. [x] Add `wallet_create_error` to all 6 language files.
5. [x] Tests: new provisioning unit tests (retries, idempotency, trustlines,
   subscribe failure, error `step`) and `cmd_start` registration coverage
   (happy path + failure keeps wallet and shows error).
6. [x] Run `just check-fast` (full `just check` run by owner/CI).
7. [x] Move plan to `docs/exec-plans/completed/` via `just finish-task`.

## Risks / Open Questions

- Registration now blocks on `create_account` + 4 trustline submits (~5-15s);
  hidden behind the existing "Loading" message, acceptable single-registration
  cost.
- `new_wallet_lock` is process-local: two bot replicas could still race on the
  master wallet sequence. Deployment is single-instance today; no change here.
- Trustlines are submitted one-by-one (same as `AddWalletNewKey`); batching is
  out of scope.
- Existing-user retry adds one Horizon GET per `/start` for free wallets; errors
  are swallowed so the main screen never regresses.
- Out of scope: the 8 historical dead wallets, paid-wallet activation, and the
  `not free_wallet` restriction in `StateSendFor`.

## Verification

- `uv run pytest bot/tests/infrastructure/test_free_wallet_provisioning.py -q`
  -> 7 passed
- `uv run pytest bot/tests/routers/test_common_start.py bot/tests/routers/test_add_wallet.py -q`
  -> 27 passed (14 + 13)
- `just check-fast` -> 654 passed, boundary/docs/plan-scope checks passed
- Expected: new user `/start` submits `create_account` + 4 `change_trust` to
  Horizon and logs `wallet_provision_completed`; a failed provisioning leaves the
  wallet row, shows `wallet_create_error`, alerts admin, and does not block the
  language screen.

## Outcome

- `/start` now provisions the free wallet on-chain right after the DB commit
  (`wallet_registration_start` -> `wallet_provision_*`), under `new_wallet_lock`.
- `AddWalletNewKey` shares the same provisioning service, so both paths can no
  longer drift apart; log keys were preserved.
- `/start` for existing free wallets retries provisioning when the on-chain
  account is missing (`wallet_provision_retry_*`), which also gives a retry path
  after a failed first attempt.
- New log markers for triage: `wallet_registration_start`,
  `wallet_registration_provisioning_failed`, `wallet_provision_start`,
  `wallet_provision_completed`, `wallet_notification_subscribe_failed`,
  `wallet_trustline_failed`.
- Historical DB-only wallets were intentionally left untouched (owner decision).
