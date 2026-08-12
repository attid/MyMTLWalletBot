# Swap Path Propagation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task.

**Goal:** Preserve the intermediate assets from the selected Horizon quote in every swap XDR.

**Architecture:** Quote helpers return the selected amount and path from one Horizon record. The router converts SDK assets to domain assets and passes them through `SwapAssets` to the existing `StellarService.swap_assets(path=...)` builder boundary.

**Tech Stack:** Python 3.12, aiogram, stellar-sdk, pytest, local mock Horizon.

---

### Task 1: Add RED router regressions

**Files:**
- Modify: `bot/tests/routers/test_swap.py`

1. Change the strict-send Horizon fixture to return a non-empty intermediate
   asset and assert the `SwapAssets.execute()` call receives the corresponding
   domain `path`.
2. Do the same for strict receive.
3. Run the two focused tests and verify they fail because `path` is missing.

### Task 2: Add RED XDR regression

**Files:**
- Modify: `bot/tests/core/test_trade_use_cases.py`

1. Pass an intermediate domain asset to `SwapAssets.execute()`.
2. Decode the returned XDR using `TransactionEnvelope.from_xdr()`.
3. Assert the operation contains the expected SDK path asset.
4. Run the focused test and verify it fails because `SwapAssets.execute()`
   does not yet accept `path`.

### Task 3: Propagate the selected path

**Files:**
- Modify: `bot/other/stellar_tools.py`
- Modify: `bot/routers/swap.py`
- Modify: `bot/core/use_cases/trade/swap_assets.py`
- Modify if required: `bot/core/interfaces/services.py`

1. Parse the `path` from the same first Horizon record used for the quote.
2. Return `(amount, need_alert, path)` from strict-send and strict-receive
   helpers.
3. Convert SDK path assets to domain assets in all four router call sites.
4. Add an optional `path` parameter to `SwapAssets.execute()` and forward it
   to `IStellarService.swap_assets()`.
5. Run the focused regressions and verify GREEN.

### Task 4: Verify and finish

**Files:**
- Modify: `docs/exec-plans/active/2026-07-15-2026-07-15-swap-path-propagation.md`

1. Run the complete swap router and trade use-case tests.
2. Run `just check-fast`.
3. Inspect `git diff --check` and the scoped diff.
4. Check all completed plan items and move the execution plan with
   `just finish-task`.
