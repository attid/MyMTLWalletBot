# assets-new-message: Make assets command send a new message

## Context

The `/assets` command should start a fresh screen by clearing scenario state and
then clearing the stored Telegram menu message id through
`clear_last_message_id(...)`. This makes the first `send_message()` call create a
new menu instead of editing a stale one.

## Files/Directories To Change

- `bot/routers/assets.py`
- `bot/tests/routers/test_assets.py`
- `AGENTS.md`
- `docs/exec-plans/completed/2026-05-23-assets-new-message.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++
> вот сделай только эти 2 правки
> добавь про ипользование clear_state и clear_last_message_id

## Change Plan

1. [x] Update `/assets` router test to require a new menu message after a stale
   `last_message_id`.
2. [x] Clear stored `last_message_id` in `cmd_assets` after `clear_state()`.
3. [x] Document the `clear_state` plus `clear_last_message_id` command-start
   pattern in `AGENTS.md`.
4. [x] Verify the `/assets` diff does not use manual `state.update_data()` for
   `last_message_id`.
5. [x] Run focused router test and `just check-fast`.

## Risks / Open Questions

- Keep the fix scoped to `/assets`; do not change shared `clear_state()`.
- Do not delete the incoming `/assets` command message in this flow.

## Verification

- `uv run pytest bot/tests/routers/test_assets.py -k assets_command_clears_last_message`
  - 1 passed, 7 deselected.
- `rg -n "await state\\.update_data\\(last_message_id=0\\)" bot/routers/assets.py`
  - No matches.
- `just check-fast`
  - ruff, mypy core, 416 tests, import boundaries, docs contract, and exec plan scope-lock passed.
