# fix-asset-display-case: Display asset codes in original case

## Context

Follow-up to case-insensitive matching fix. Messages displayed uppercased
asset codes (e.g. "TIMELINE") instead of original case from Stellar ("timeline").

## Files/Directories To Change

- `bot/routers/swap.py`
- `bot/routers/trade.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> User reported cosmetic issue via screenshot showing uppercased display.

## Change Plan

1. [x] After finding `found_from`, reassign `from_code = found_from.asset_code` in swap.py.
2. [x] After finding `found_to`, reassign `to_code = found_to.asset_code` in swap.py.
3. [x] After finding `sell_asset`, reassign `sell_code = sell_asset.asset_code` in trade.py.
4. [x] After finding `buy_asset`, reassign `buy_code = buy_asset.asset_code` in trade.py.
5. [x] `just check-fast` passes.

## Risks / Open Questions

- None.

## Verification

- `just check-fast`: 356 passed, all linters green.
