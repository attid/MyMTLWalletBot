# free-wallet-xlm-policy: Free-wallet safe PathPayment and ClaimableBalance XDR policy

## Context

Diagnostics Docker3 #99 and reconnaissance #100: a free wallet
(`wallet.is_free=True`) cannot sign MTLCROWD donations because
`stellar_check_xdr` rejects `PathPaymentStrictReceive` and
`CreateClaimableBalance` wholesale. The invariant is "a free wallet must not
spend its own native XLM", not "all path/CB operations are forbidden".

Effective operation source is `operation.source` when present, otherwise
`transaction.source`. A signature does not imply source, so co-signing by a
free wallet must not be blocked merely because the wallet signs.

Design decision will be recorded in
`adr/0003-free-wallet-xlm-spend-policy.md`.

## Files/Directories To Change

- `bot/other/stellar_tools.py`
- `bot/other/tx_render.py`
- `bot/routers/sign.py`
- `bot/infrastructure/services/stellar_service.py`
- `bot/core/interfaces/services.py`
- `bot/langs/*.json`
- `bot/tests/other/test_stellar_tools.py`
- `bot/tests/other/test_free_wallet_xdr_policy.py`
- `bot/tests/other/test_tx_render.py`
- `bot/tests/routers/test_sign.py`
- `bot/tests/routers/test_sign_tools_description.py`
- `adr/0003-free-wallet-xlm-spend-policy.md`
- `docs/exec-plans/active/2026-10-24-free-wallet-xlm-policy.md`
- `docs/exec-plans/completed/2026-10-24-free-wallet-xlm-policy.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> Task f5a9afc6a3f84577aabd263fb2ef9859 explicitly orders: "Исправить проверку
> XDR для free-кошельков ... разрешить безопасные PathPaymentStrictSend,
> PathPaymentStrictReceive и CreateClaimableBalance ... Добавить регрессионные
> unit/router-тесты ... Оформить короткий ADR ... Прогнать точечные тесты, затем
> штатные гейты just". The listed paths are the minimal implementation, test,
> localization, and ADR scope required by that order; no `.env`, secrets,
> deployments, neighboring projects, or commits/pushes are involved.

## Change Plan

1. [x] `stellar_tools.py`: add effective-source resolution (operation source,
       else transaction source; G-address of muxed accounts), allow
       PathPaymentStrictSend/StrictReceive only when `send_asset` is not native
       for a free effective source, allow CreateClaimableBalance only when
       `asset` is not native for a free effective source, keep Payment/Soroban
       guards, fail closed on fee-bump/unknown source/asset.
2. [x] Surface free-wallet rejection as a dedicated error and map it in
       `routers/sign.py` to a localized message without echoing raw XDR; keep
       generic `bad_xdr` for all other causes.
3. [x] `stellar_service.py` / `core/interfaces/services.py`: pass the free
       wallet public key through the existing DI boundary.
4. [x] `tx_render.py`: minimal human-readable rendering for PathPayment and
       CreateClaimableBalance.
5. [x] Add regression tests for path/CB matrix, effective source (op/tx/muxed),
       co-signer, multi-op, invalid XDR, fee-bump, existing Payment/Soroban
       guards, and the #99-style donation case; add a router test for the
       free-wallet rejection message.
6. [x] Add ADR `0003-free-wallet-xlm-spend-policy.md` and document fee/reserve
       limitations without changing reserve rules.
7. [x] Run targeted tests, then `just lint`, `just test-fast`, `just arch-test`
       (and `just check-fast` if time allows).
8. [x] Move plan to `docs/exec-plans/completed/` only when all Change Plan
       items are checked (no commit/push/deploy in this task).

## Risks / Open Questions

- Reserves and network fees are still paid in XLM by the transaction source;
  this policy only guards XLM spent as an operation asset. Reserve/fee rules
  are unchanged and need a separate product decision.
- Fee-bump and sponsored-reserve flows remain unsupported; they fail closed.
- Product boundary for free-wallet operation fees remains open.

## Verification

- `PYTHONPATH=. .venv/bin/python -m pytest bot/tests/other/test_stellar_tools.py bot/tests/other/test_tx_render.py bot/tests/routers/test_sign.py -q`
- `just lint`
- `just test-fast`
- `just arch-test`
- `just check-fast`

Results (2026-10-24): targeted 71 passed; `just check-fast` green (573 passed); `just test` 963 passed, 8 deselected.
