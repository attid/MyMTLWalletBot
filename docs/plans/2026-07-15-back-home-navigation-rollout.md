# Repository-wide Back/Home Navigation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Apply the established Send/Swap Back-versus-Home navigation contract to the approved bot functions in product-priority order.

**Architecture:** Reuse `FlowBack` for active FSM transitions and existing explicit parent callbacks for non-FSM menu hierarchy. Implement each priority area through a separate execution mini-plan with its own transition/data-invalidation table and TDD regressions; legacy TON and deferred Cheques are explicitly outside this rollout.

**Tech Stack:** Python 3.12, aiogram FSM/router callbacks, pytest with `mock_telegram`, Redis-backed notification coordination, Ruff, Mypy.

---

## Execution Model

This file is the master plan. Do not implement all tasks in one patch. For each
functional task below:

1. Create `docs/exec-plans/active/<date>-<slice>.md` with exact allowed paths.
2. Derive and record every current state→previous state/menu transition before
   editing runtime code.
3. Record which FSM keys survive and which later-step/signing keys are removed.
4. Execute RED/GREEN tests and implementation as a standalone change.
5. Finish the mini-plan and commit the slice before starting the next one.

The approved order is Trade, Assets, MTL Tools/MTLAP, wallet
onboarding/signing, used-function audit, then repository-wide regression.

## Explicit Scope Boundaries

- Do not modify `bot/routers/ton.py`; TON is legacy.
- Do not modify `bot/routers/cheque.py`; Cheques are deferred to a future
  separately approved task.
- Do not pull either function back into scope during the general audit.
- Notification-message keyboards remain Settings + Home under their existing
  delivery contract.
- Successful, submitted, destructive, or externally completed terminal screens
  stay Home-only.

### Task 1: Lock the existing Send/Swap contract as the baseline

**Files:**
- Modify only for a genuine missing shared regression: `bot/keyboards/common_keyboards.py`
- Modify only for a genuine missing activity regression: `bot/middleware/notification_activity.py`
- Test: `bot/tests/middleware/test_notification_activity.py`
- Test: `bot/tests/routers/test_send.py`
- Test: `bot/tests/routers/test_swap.py`

**Steps:**

1. Run the existing Send/Swap FlowBack and middleware regressions.
2. Verify they cover localized Back/Home labels, active-FSM-only notification
   touches, previous-step rendering, selective FSM-data retention, stale
   signing-data invalidation, and terminal Home-only screens.
3. Add a failing shared regression only for an established guarantee that is
   not mechanically covered.
4. Make the minimal helper/middleware change needed for that regression; do not
   add navigation history, a screen stack, or a new callback namespace.
5. Run:
   `uv run pytest bot/tests/routers/test_send.py bot/tests/routers/test_swap.py bot/tests/middleware/test_notification_activity.py -q`.
6. Expect all focused tests to pass. Commit separately only if this baseline
   task required runtime/test changes.

### Task 2: Add Back/Home to Trade and order management

**Files:**
- Modify: `bot/routers/trade.py`
- Test: `bot/tests/routers/test_trade.py`
- Reuse: `bot/keyboards/common_keyboards.py`
- Reuse contract: `bot/infrastructure/services/signing_facade.py`

**Steps:**

1. Create the Trade mini-plan and map New Order transitions from sell asset to
   buy asset, sell amount, receive amount, and pre-submit confirmation.
2. Separately map Show Orders→order detail→edit amount/edit price using the
   existing render functions and typed callback data.
3. Write failing router tests for every legal reverse edge.
4. Add failing tests showing invalid amount/price keeps the current state with
   the same Back and Home controls.
5. Add signing-boundary tests proving Back from a built order immediately
   removes `PENDING_SIGNATURE_REQUEST_KEY`, XDR, operation, sign message,
   success message, and flow-specific completion callbacks.
6. Implement state-specific `FlowBack` handlers by reusing current renderers.
7. For non-FSM list/detail hierarchy, show the existing parent callback as Back
   and keep a distinct `Return` Home; do not create FSM solely for navigation.
8. Verify successful create/edit/delete screens contain no Back and cannot
   replay the completed operation.
9. Run `uv run pytest bot/tests/routers/test_trade.py -q`,
   `just test-e2e-smoke`, and `just check-fast`.
10. Finish the mini-plan and commit:
    `feat(navigation): add Back actions to trade flows`.

### Task 3: Add Back/Home to Assets and wallet settings

**Files:**
- Modify: `bot/routers/wallet_setting.py`
- Modify: `bot/keyboards/assets.py`
- Modify only if parent rendering requires it: `bot/routers/assets.py`
- Test: `bot/tests/routers/test_wallet_setting.py`
- Test: `bot/tests/routers/test_wallet_setting_visibility.py`
- Test: `bot/tests/routers/test_assets.py`
- Reuse: `bot/keyboards/common_keyboards.py`

**Steps:**

1. Create the Assets mini-plan with separate transition tables for asset
   add/delete/visibility, expert code→issuer entry, address book, wallet
   selection, manage-data, and security submenus.
2. Write failing tests for every FSM reverse edge.
3. Write failing tests for every existing non-FSM parent-menu callback that
   needs a distinct Home button.
4. Preserve selected wallet/asset data required by the previous screen and
   remove issuer, destructive-confirmation, XDR, and signing fields owned by
   abandoned later steps.
5. Implement FSM Back with `FlowBack` and menu Back with existing typed callback
   data.
6. Verify completed trustline/security/data operations and private-key display
   do not gain an unsafe replay path.
7. Run the three focused suites, `just test-e2e-smoke`, and `just check-fast`.
8. Finish the mini-plan and commit:
   `feat(navigation): add Back actions to wallet assets`.

### Task 4: Add Back/Home to MTL Tools and MTLAP Tools

**Files:**
- Modify: `bot/routers/mtltools.py`
- Modify: `bot/routers/mtlap.py`
- Test: `bot/tests/routers/test_mtltools.py`
- Test: `bot/tests/routers/test_mtlap.py`
- Reuse: `bot/keyboards/common_keyboards.py`
- Reuse contract: `bot/infrastructure/services/signing_facade.py`

**Steps:**

1. Create the Tools mini-plan and map delegate, donation
   address→name→percent, BIM address→name, and MTLAP recommendation/delegate
   transitions independently.
2. Map existing list/detail parent callbacks separately from active FSM steps.
3. Write failing tests for every form reverse edge and list/detail parent
   action.
4. Add tests proving Back from every built Tools transaction invalidates its
   pending signature and XDR immediately.
5. Implement form Back one field at a time, reusing current prompt renderers and
   preserving only data valid for the earlier field.
6. Add distinct Home beside existing menu Back actions and keep successful tool
   updates Home-only.
7. Run both focused suites, `just test-e2e-smoke`, and `just check-fast`.
8. Finish the mini-plan and commit:
   `feat(navigation): add Back actions to MTL tools`.

### Task 5: Add Back/Home to wallet onboarding, PIN/password, and signing

**Files:**
- Modify: `bot/routers/add_wallet.py`
- Modify: `bot/routers/sign.py`
- Modify only if state ownership requires it: `bot/infrastructure/states.py`
- Test: `bot/tests/routers/test_add_wallet.py`
- Test: `bot/tests/routers/test_sign.py`
- Test: `bot/tests/test_signing_flow.py`
- Reuse: `bot/keyboards/webapp.py`

**Steps:**

1. Create the onboarding/signing mini-plan and map Add Wallet menu→private or
   public key prompt→PIN/password choice→credential setup.
2. Map PIN/password first entry, confirmation/retry, and signing-password entry;
   classify existing WebApp/biometric cancellation screens separately from
   editable Back transitions.
3. Write failing tests for every legal Back edge.
4. Add explicit tests that secret text, PIN/password values, and consumed
   signing requests are cleared and never rendered after Back.
5. Implement `FlowBack` only for active editable states; retain existing cancel
   callbacks at WebApp/biometric or already-submitted boundaries.
6. Verify Home completes notification flow for local and WebApp signing, while
   failed submission neither reports success nor reopens a signed payload.
7. Run the three focused suites, `just test-e2e-smoke`,
   `just test-external`, and `just check-fast`.
8. Finish the mini-plan and commit:
   `feat(navigation): add Back actions to wallet onboarding`.

### Task 6: Audit remaining actively used functions

**Files to inspect first:**
- `bot/routers/inout.py`
- `bot/routers/common_start.py`
- `bot/routers/fest.py`
- `bot/routers/bsn.py`
- `bot/routers/common_setting.py`
- `bot/routers/notification_settings.py`
- `bot/routers/start_msg.py`
- `bot/routers/uri.py`
- `bot/keyboards/webapp.py`
- Corresponding files under `bot/tests/routers/`

**Steps:**

1. Inventory every remaining inline keyboard containing `Return`, a localized
   Back label, or a callback that renders a parent menu.
2. Confirm which candidate functions are actively used before proposing any
   runtime edit.
3. Explicitly exclude `bot/routers/ton.py` and `bot/routers/cheque.py` from the
   audit results.
4. Classify each used screen as intermediate FSM, nested callback menu, entry,
   irreversible terminal, external cancel boundary, or notification screen.
5. Create a separate user-approved mini-plan per material used function; do not
   combine unrelated legacy routers into one patch.
6. For each approved mini-plan, follow TDD, reuse existing parent renderers, and
   run its focused suite plus `just check-fast`.
7. Record unused/deferred findings in the audit plan without changing their
   runtime code.

### Task 7: Run repository-wide navigation regression

**Files:**
- Modify only for genuine gaps: `bot/tests/routers/`
- Modify only for genuine gaps: `bot/tests/middleware/test_notification_activity.py`
- Update: `docs/plans/2026-07-15-back-home-navigation-rollout-design.md`
- Update: `docs/plans/2026-07-15-back-home-navigation-rollout.md`

**Steps:**

1. Re-run the inline-keyboard inventory and account for every changed screen.
2. Confirm the final inventory still marks TON legacy and Cheques deferred.
3. Verify Back→previous-step, Home→FSM clear/notification completion, selective
   data retention, signing invalidation, active-hold behavior, and terminal
   Home-only behavior across every implemented slice.
4. Add a mechanical regression or lint check only if it can distinguish screen
   classes without false positives.
5. Run `just fmt`, `just lint`, `just test`, `just arch-test`,
   `just test-e2e-smoke`, `just test-external`, and `just secret-scan`.
6. Manually smoke one local-signing and one WebApp-signing transaction: Back
   before submit, Home before submit, success followed by Home, and pending
   notification release.
7. Confirm a stale `FlowBack` cannot touch notification hold without active FSM
   and no terminal transaction can be replayed.
8. Finish the final execution plan and commit the regression/audit updates.

## Recommended Next Step

Create the Task 2 mini-plan for Trade and order management. It is the highest
product priority and should be completed and reviewed before starting Assets.
