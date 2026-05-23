# send-muxed-payment-check: Use base account for muxed payment existence check

## Context

The send flow now uses the underlying `G...` account for muxed-address token
selection, but payment preparation still checks destination existence using the
original `M...` address. Horizon account existence checks must use the
underlying account, while the transaction destination must remain the original
muxed address.

## Files/Directories To Change

- `bot/core/use_cases/payment/send_payment.py`
- `bot/routers/send.py`
- `bot/tests/core/test_payment_use_cases.py`
- `bot/tests/routers/test_send.py`
- `docs/exec-plans/completed/2026-05-23-send-muxed-payment-check.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add failing tests for muxed payment existence checks after amount entry.
2. [x] Extend `SendPayment.execute()` with an optional destination check address.
3. [x] Pass `send_balance_address` from `cmd_send_04()` for existence checks.
4. [x] Keep payment transaction destination as the original `send_address`.
5. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Create-account flow should keep its current behavior.
- Do not replace muxed destination with the underlying account in the payment op.

## Verification

- `uv run pytest bot/tests/core/test_payment_use_cases.py -k muxed`
  - Red before fix: unexpected `destination_check_address` argument.
  - Green after fix: 1 passed, 5 deselected.
- `uv run pytest bot/tests/routers/test_send.py -k muxed`
  - Red before fix: router did not pass `destination_check_address`.
  - Green after fix: muxed get-sum test passed.
- `uv run pytest bot/tests/core/test_payment_use_cases.py bot/tests/routers/test_send.py`
  - 20 passed.
- `just check-fast`
  - ruff, mypy core, 417 tests, import boundaries, docs contract, and exec plan scope-lock passed.
