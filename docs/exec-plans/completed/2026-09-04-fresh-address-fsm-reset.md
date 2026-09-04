# fresh-address-fsm-reset: Reset stale transaction context for direct address flow

## Context

Starting a transfer by sending a plain Stellar address reuses FSM data from the
previous completed transaction. Stale memo and callback routing then leak into the new
payment even though the FSM state label itself was reset.

## Files/Directories To Change

- `bot/routers/common_end.py`
- `bot/tests/routers/test_common_end.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Reproduce stale memo leakage into a new direct-address transfer.
2. [x] Reproduce stale callback/return routing retained for the new transfer.
3. [x] Clear transient FSM data and the tracked UI message when a valid address starts
   a fresh transfer, before storing its recipient data.
4. [x] Preserve user/session fields and destination-provided memo behavior.
5. [x] Run targeted tests, `just check-fast`, and `just check`.

## Risks / Open Questions

- The destination user id returned by username lookup must never be used to clear the
  sender's FSM; cleanup must use `message.from_user.id`.
- Invalid/unresolved addresses must not discard the current flow.

## Verification

- `uv run --package mmwb-bot pytest bot/tests/routers/test_common_end.py`
- `just check-fast`
- `just check`
- A valid new address clears stale transaction metadata while ordinary and invalid
  inputs retain existing behavior.
