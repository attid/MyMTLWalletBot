# direct-transfer-ui-replacement: Preserve tracked UI message during direct transfer reset

## Context

The direct-address flow correctly clears transient FSM data, but clearing the tracked
message id before `need_new_msg=True` prevents the sender from deleting the previous UI
screen and can leave an extra stale screen in chat.

## Files/Directories To Change

- `bot/routers/common_end.py`
- `bot/tests/routers/test_common_end.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> давай, я тоже опасаюсь что лишний экран появиться

## Change Plan

1. [x] Reproduce the stale previous UI message in the direct-address flow.
2. [x] Preserve `last_message_id` through transient FSM cleanup so
   `need_new_msg=True` can replace the tracked screen.
3. [x] Keep stale transaction-data cleanup unchanged.
4. [x] Run targeted tests, `just check-fast`, and `just check`.

## Risks / Open Questions

- The new screen must become the tracked message after the old one is deleted.
- No transaction-specific fields may survive the cleanup.

## Verification

- `uv run --package mmwb-bot pytest bot/tests/routers/test_common_end.py`
- `just check-fast`
- `just check`
- The old tracked message is deleted and the fresh token screen remains tracked.
