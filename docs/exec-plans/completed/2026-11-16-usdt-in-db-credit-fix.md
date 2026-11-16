# usdt-in-db-credit-fix: Fix USDT_IN DB credit regression (full balance instead of income)

## Context

Support ticket `#ID175150644` (@VitaliiKrutko): 4 USDT TRC20 deposits of 500, only 3
credited with USDM, the 3rd one is stuck on `USDT account balance unchanged`, and
`/check_usdt` reports `DB Balance: 3500` vs `Chain Balance: 2000.001`.

Root cause: regression in commit `88819fb` ("Introduce new repository interfaces...").
`cmd_usdt_check` used to credit the **income delta** (`db_update_usdt_sum(...,
update_summ=income_usdt_balance)`), but after the refactor it credits the **full chain
balance** into an *incremental* repository method:

`bot/routers/inout.py:297`
```python
await user_repo.update_usdt_balance(get_user_id(callback), full_usdt_balance)
```

`SqlAlchemyUserRepository.update_usdt_balance` is additive
(`user.usdt_amount = current_amount + amount`), so every successful check turns
`DB = DB + chain`. After two 500-deposits the DB drifts above the chain balance and
every following deposit fails the `income_usdt_balance < min_usdt_sum` gate, while the
USDT sweep later zeroes the inflated DB — losing the pending USDM payout.

## Files/Directories To Change

- `bot/routers/inout.py`
- `bot/tests/routers/test_inout.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> «4 не надо. 1 2 давай сделаем. я потом обновлю и сделаю 3»
> (items 1 = fix in `bot/routers/inout.py`, 2 = test update; item 4/Broad audit and
> item 3/user data repair are explicitly out of scope, owner does them manually)

## Change Plan

1. [x] `bot/routers/inout.py`: credit `income_usdt_balance` (delta) instead of
       `full_usdt_balance` in `cmd_usdt_check`.
2. [x] `bot/tests/routers/test_inout.py`: assert `update_usdt_balance` is awaited with
       the income delta, so the regression cannot silently return.
3. [x] Run validation: `just lint`, `just test-fast`, `just arch-test`.
4. [x] No docs update needed (behavior restored to pre-regression contract).
5. [x] Run `just check`.

## Risks / Open Questions

- Users already affected by the drift (`DB > chain`) need manual `/set_usdt` repair by
  the owner; DB drift is not self-healed by this fix.
- Pre-existing, out-of-scope risks (owner decision pending): DB is credited before the
  Stellar payout succeeds, and the USDT sweep can move an unchecked deposit to master.

## Verification

- `just test-fast` — 712 passed.
- `just lint` — ruff + mypy clean.
- `just arch-test` — all three guardrails passed.
- `ruff format --check` — clean.
- New assertion fails on the old code (`full_usdt_balance == 100`) and passes on the
  fix (`income_usdt_balance == 50`).
- Manual reasoning check: 2 deposits of 500 -> DB equals chain (1000), 3rd deposit of
  500 -> `income_usdt_balance == 500` and DB becomes 1500.
- Follow-up (owner, out of scope): `/set_usdt vitaliikrutko` repair after deploy.
