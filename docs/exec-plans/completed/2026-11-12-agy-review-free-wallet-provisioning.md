# agy-review-free-wallet-provisioning: Fixes from external AGY review

## Context

Continuation of `docs/exec-plans/completed/2026-11-11-free-wallet-provisioning.md`
(free wallet provisioning on `/start`). The owner asked for an external AGY review
of the uncommitted changes. Three review rounds were run, must-have findings fixed,
the rest recorded as backlog / accepted risks.

Reports:

- `docs/drafts/agy_free_wallet_provisioning_round1_review.md`
- `docs/drafts/agy_free_wallet_provisioning_round2_review.md`
- `docs/drafts/agy_free_wallet_provisioning_round3_review.md` (verdict: commit)

## Files/Directories To Change

- `bot/infrastructure/services/free_wallet_provisioning.py`
- `bot/routers/common_start.py`
- `bot/routers/add_wallet.py`
- `bot/tests/infrastructure/test_free_wallet_provisioning.py`
- `bot/tests/routers/test_common_start.py`
- `docs/drafts/` (review reports)
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> Owner requested the review ("сделай аги ревью (такой скил в ОВ)") on top of the
> already approved free-wallet-provisioning scope; the skill requires fixing
> must-have findings. Same paths as the parent plan plus review reports.

## Change Plan

1. [x] Round 1: fix P1 (error message overwritten by language screen), P2 (admin
   alert HTML parse mode, trustline top-up on retry), P3 (`check_account` for a
   fresh key, `use_pin != 0`, remove `assert` from control flow).
2. [x] Round 2: `ensure_provisioned(assets=...)` creates only missing trustlines;
   replace `check_account` with caller-known `account_exists` (no extra Horizon GET
   under `new_wallet_lock`); truncate alert error text to 1000 chars.
3. [x] Round 3: regression check, no P1/P2/P3 left; verdict "commit".
4. [x] Tests: realistic failure UI without mocked `cmd_language`, admin alert
   (parse_mode, length, swallowed delivery error), partial trustline top-up,
   decrypt-failure early exit, TON/PIN/read-only skips, retry failure does not
   block the balance screen.
5. [x] Run `just check-fast` and focused tests.
6. [x] Move plan to completed with `just finish-task`.

## Risks / Open Questions

- Backlog (agreed, not a blocker): no backoff between `create_account` retries.
- Backlog (agreed): Horizon 5xx/timeout is indistinguishable from 404 because
  `StellarService.get_account_details` swallows both; a retry may attempt
  `create_account` three times under the lock during an outage. Failures are fast,
  no data loss, main screen still renders. Fixing it needs a strict Horizon probe
  (new service/interface method) - out of scope here.
- Rejected: removing `ProvisionResult` (tests use it as result contract).

## Verification

- `uv run pytest bot/tests/infrastructure/test_free_wallet_provisioning.py -q`
  -> 10 passed
- `uv run pytest bot/tests/routers/test_common_start.py bot/tests/routers/test_add_wallet.py -q`
  -> 37 passed (24 + 13)
- `just check-fast` -> 657 passed, boundary/docs/plan-scope checks passed
  (note: `test-fast` skips `tests/routers`, so router coverage was verified with
  the commands below)
- `just test-e2e-smoke` -> 144 passed
- `just test` -> 1073 passed, 8 deselected
