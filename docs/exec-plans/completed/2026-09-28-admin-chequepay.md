# admin-chequepay: Admin payout commands /chequepay and /withdraw

## Context

Admin-only Stellar payout commands (bot/routers/admin.py):
- `/chequepay <адрес> <сумма>` — payment from the cheque treasury account
  (CHEQUE_PUBLIC_KEY), EURMTL implied, no memo argument (user decision m00847/m00856).
- `/withdraw <адрес> <сумма> <ассет> [memo]` — payment from the master wallet
  (user_id=0 default wallet), asset whitelist EURMTL/MTL/SATSMTL/USDM/USDC/BTCMTL/XLM.
Both need explicit confirmation buttons (✅ Отправить / ❌ Отмена, user m00856) and
must be listed in /help.

## Files/Directories To Change

- `bot/routers/admin.py`
- `bot/tests/routers/test_admin.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> m00847: «/chequepay норм. запрет на редактировнаие.»
> m00856: «ок давай подтверждение сделам. мемо не нужно»
> m00813 (paraphrased): /withdraw stays for transfer from the main account; cheque
> payout separate command without asset arg, add both to /help.
> (Execution plan file itself created via `just start-task` per repo workflow.)

## Change Plan

1. [x] `bot/routers/admin.py`: add `/chequepay` handler — parse address+amount,
   amount `f"{float(x):.7f}"`, confirmation summary + inline ✅/❌ buttons.
2. [x] `bot/routers/admin.py`: add `/withdraw` handler — parse address+amount+asset
   (whitelist, XLM→native), optional memo, same confirmation flow.
3. [x] `bot/routers/admin.py`: callback_query handlers (approve/cancel) with
   explicit `from_user.id in config.admins` check (router message filter does not
   cover callbacks); execute: master/cheque source wallet via
   `wallet_repo.get_default_wallet`, secret decrypt (crypto_v2 free-mode → legacy
   `decrypt(secret_key, "0")`), `build_payment_transaction` → `sign_xdr` →
   `submit_transaction` → `result["successful"]` check + `format_horizon_send_error`
   on failure (pattern cmd_cancel_cheque, bot/routers/cheque.py:534-554).
4. [x] `bot/routers/admin.py`: add both commands to /help list (admin.py:487-503).
5. [x] `bot/tests/routers/test_admin.py`: tests for success, non-admin callback
   rejection, bad arguments, Horizon rejection, cancel path.
6. [x] Run `just check-fast` (lint + test-fast + arch-test).

## Risks / Open Questions

- Risk: irreversible payment on typos — mitigated by confirmation buttons.
- Risk: admin filter does not cover callback_query — mitigated by explicit
  from_user.id check in both callbacks.
- Question: none open (name /chequepay, buttons yes, memo no — user confirmed).

## Verification

- `just check-fast` green (lint, test-fast, arch-test).
- New tests in bot/tests/routers/test_admin.py pass; full test-fast suite green.
- Manual sanity: handlers reject bad usage without submitting anything.