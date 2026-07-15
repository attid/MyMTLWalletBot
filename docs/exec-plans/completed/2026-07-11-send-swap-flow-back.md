# send-swap-flow-back: Add state-aware back navigation to send and swap

## Context

Send and Swap currently use the global `Return` action, which clears FSM and
returns home. Add a flow-local back action for intermediate steps. Successful
terminal screens keep the existing home action. Flow-local back counts as user
activity and extends the notification hold; home completes the flow and flushes
pending blockchain notifications. Notification-message navigation is out of
scope and must remain unchanged.

## Files/Directories To Change

- `bot/routers/send.py`
- `bot/routers/swap.py`
- `bot/keyboards/common_keyboards.py`
- `bot/middleware/notification_activity.py`
- `bot/tests/routers/test_send.py`
- `bot/tests/routers/test_swap.py`
- `bot/tests/middleware/test_notification_activity.py`
- `docs/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++"

## Change Plan

1. [x] Map each supported Send/Swap intermediate FSM state to its semantic
   previous step and add failing router tests.
2. [x] Add a dedicated `FlowBack` callback/keyboard helper that preserves FSM
   data and rerenders the previous step.
3. [x] Keep successful terminal screens on global `Return`/home and verify they
   call flow completion.
4. [x] Classify `FlowBack` as meaningful activity so it extends the hold, while
   global home remains completion/flush behavior.
5. [x] Run focused tests, `just check-fast`, E2E/external checks, and secret scan.

## Risks / Open Questions

- Back mappings must not allow returning to a transaction after it has been
  submitted successfully.
- Existing notification keyboards and `Return` behavior must not change.

## Verification

- Focused FlowBack router regressions: `21 passed`.
- `just check-fast`: passed, including `546 passed`, Ruff, core mypy,
  architecture, docs-contract, and scope-lock checks.
- `just test-e2e-smoke`: `117 passed`.
- `just test-external`: `7 passed`, including real Redis and notifier flow.
- `just secret-scan`: passed; no leaks found.
- Independent Terra final review: `APPROVE`.
- Regression coverage verifies immediate invalidation of stale signing data,
  QR/memo navigation, and preservation of `last_message_id` and global state.
