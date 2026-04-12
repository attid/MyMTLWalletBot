# fix-case-insensitive-asset-match: Case-insensitive asset code matching in swap/trade

## Context

Stellar Horizon API returns asset codes in their original case (e.g. `timeline`),
but `/swap` and `/trade` commands uppercased user input and compared with strict equality,
causing "asset not found" errors for mixed-case assets.

## Files/Directories To Change

- `bot/routers/swap.py`
- `bot/routers/trade.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> User reported bug via screenshot and asked to fix it.

## Change Plan

1. [x] Add `.upper()` to `b.asset_code` in matching list comprehensions in `swap.py` (lines 218, 239).
2. [x] Add `.upper()` to `b.asset_code` in matching list comprehensions in `trade.py` (lines 334, 362).
3. [x] Run `just check-fast` — all 356 tests pass, linters and arch-tests pass.

## Risks / Open Questions

- None. Minimal 4-line diff, existing tests cover the changed paths.

## Verification

- `just check-fast` passes (356 tests, import boundaries, docs contract, scope-lock).
- Full test suite: 566 passed.
