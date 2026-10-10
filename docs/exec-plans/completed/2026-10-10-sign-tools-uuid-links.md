# sign-tools-uuid-links: Accept 32-char uuid sign_tools links in get_eurmtl_xdr

## Context

Production breakage 2026-10-10: bot stopped loading transactions from
eurmtl.me sign_tools links — `bad sign_tools hash:
'7bc7d48c16e34b129821eb8f85563b88'`. Root cause: the strict hex-64
validation added in 0dc2f92 rejected links where the id is a 32-char
uuid hex. eurmtl.me creates such links for rely-deal transactions
(`routers/rely.py` uses `add_transaction` result, which can be the
transaction uuid, not the stellar hash). The eurmtl.me API contract
already accepts both: `remote/get_xdr/<id>` allows len 64 and len 32,
routed by length in `TransactionService.get_transaction_by_hash`.
Verified live: `GET https://eurmtl.me/remote/get_xdr/7bc7d48c16e34b129821eb8f85563b88`
→ 200 with xdr + description.

## Files/Directories To Change

- `bot/other/stellar_tools.py`
- `bot/tests/other/test_stellar_tools.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> Owner reported the breakage and ordered the fix directly: «да косяк я не
> просил доабвлять проверки ... можешь поправить и закомит\пуш ?»

## Change Plan

1. [x] `stellar_tools.py` `get_eurmtl_xdr`: regex accepts 64-char stellar
       hash or 32-char uuid hex, comment documents the API contract.
2. [x] Regression tests: parametrized hash-64 / uuid-32 links reach the API
       with the correct id; malformed id is rejected without an API call.
3. [x] Run lint + full bot test suite.

## Risks / Open Questions

- None: validation still rejects non-hex ids; the 32-char branch only
  widens the accepted set to what the API already serves.

## Verification

- `uv run ruff check` + `ruff format --check` on changed files — green.
- Full suite: 925 passed, 8 deselected (was 922 + 3 new tests).
