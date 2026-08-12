# 2026-07-15-swap-path-propagation: Preserve Horizon swap paths in XDR

## Context

`/swap 2 usdm mtl` quotes the best Horizon strict-send path but builds an XDR
with an empty path. The quoted `dest_min` belongs to a multi-hop route while
the transaction executes the direct market and fails with
`op_under_dest_min`. Strict-receive and menu-driven swaps use the same lossy
data flow.

## Files/Directories To Change

- `bot/routers/swap.py`
- `bot/other/stellar_tools.py`
- `bot/core/use_cases/trade/swap_assets.py`
- `bot/core/interfaces/services.py`
- `bot/tests/routers/test_swap.py`
- `bot/tests/core/test_trade_use_cases.py`
- `docs/exec-plans/`
- `docs/plans/2026-07-15-swap-path-propagation-design.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User answered `++` after the exact paths were listed, then answered `++`
> again after approving the amount-plus-path propagation design and regression
> test strategy.

## Change Plan

1. [x] Add RED regression coverage proving a non-empty Horizon path must be
       present in the built strict-send and strict-receive XDR operations.
2. [x] Change the legacy quote helpers to return the selected Horizon path
       together with the quoted amount and alert flag.
3. [x] Propagate the selected path through `routers/swap.py`, `SwapAssets`, and
       `IStellarService.swap_assets` into `StellarService.swap_assets`.
4. [x] Run focused swap tests and confirm GREEN.
5. [x] Run `just check-fast` and inspect the final diff.

## Risks / Open Questions

- Horizon quote and transaction construction must use the same record; a
  second pathfinding request inside the builder would introduce a race and is
  intentionally avoided.
- Existing uncommitted work overlaps `bot/routers/swap.py` and
  `bot/tests/routers/test_swap.py`; preserve those changes and keep this diff
  narrowly scoped.

## Verification

- RED: router regressions failed with missing `path`; the use-case regression
  failed because `SwapAssets.execute()` did not accept `path`.
- GREEN: `uv run pytest bot/tests/routers/test_swap.py
  bot/tests/core/test_trade_use_cases.py -q` -> `25 passed`.
- Direct-route XDR decodes with `path=[]`; strict-send and strict-receive XDRs
  decode with the expected `SATSMTL` intermediate asset.
- `just check-fast` -> Ruff and Mypy clean, `548 passed`, import/docs/scope
  guardrails passed.
