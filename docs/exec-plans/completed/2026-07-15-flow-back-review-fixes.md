# flow-back-review-fixes: Close state-safety review findings

## Context

Final review of state-aware Send navigation found that returning from a built
confirmation all the way to the recipient prompt could retain the old signing
payload. It also found that a stale `FlowBack` callback without an active FSM
could unnecessarily extend the notification hold.

## Files/Directories To Change

- `bot/routers/send.py`
- `bot/routers/swap.py`
- `bot/middleware/notification_activity.py`
- `bot/tests/routers/test_send.py`
- `bot/tests/routers/test_swap.py`
- `bot/tests/middleware/test_notification_activity.py`
- `docs/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> User authorized the original FlowBack paths with "++".

## Change Plan

1. [x] Add a failing multi-step Send regression for stale signing payloads.
2. [x] Clear recipient, selection, amount, and signing payload state when Back
   returns to the recipient prompt while preserving global UI state.
3. [x] Invalidate stale signing payloads immediately when Back leaves a Send
   or Swap confirmation screen.
4. [x] Restrict FlowBack notification touches to active FSM flows.
5. [x] Run focused tests, repository gates, E2E/external tests, secret scan,
   and final review.

## Risks / Open Questions

- `last_message_id` and unrelated/global FSM data must be preserved.
- Home/Return and notification delivery behavior must remain unchanged.

## Verification

- TDD red phase: three confirmation-back regressions failed because stale
  signing payloads remained.
- TDD green phase: the same three regressions passed after immediate signing
  invalidation.
- All focused FlowBack router regressions: `21 passed`.
- `just check-fast`: passed, including `546 passed`, Ruff, core mypy,
  architecture, docs-contract, and scope-lock checks.
- `just test-e2e-smoke`: `117 passed`.
- `just test-external`: `7 passed`.
- `just secret-scan`: passed; no leaks found.
- Independent Terra final review: `APPROVE`.
