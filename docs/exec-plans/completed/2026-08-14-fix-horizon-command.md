# fix-horizon-command: Fix Horizon RW command registration

## Context

The Telegram admin command menu registers `/horizon_rx`, while the admin router
handles `/horizon_rw`. Selecting the menu command therefore reaches the fallback
router and is deleted instead of switching the read/write Horizon URL.

## Files/Directories To Change

- `bot/start.py`
- `bot/tests/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++ только тест тогда на все команды делай наврено"

## Change Plan

1. [x] Add a startup test that asserts the complete private and admin command
   registrations, including their Telegram scopes.
2. [x] Run the new test and confirm it fails because the admin menu contains
   `horizon_rx` instead of `horizon_rw`.
3. [x] Correct the registered admin command in `bot/start.py`.
4. [x] Run the focused startup tests and the repository fast gate.
5. [x] Finish this execution plan after all checks pass.

## Risks / Open Questions

- Exact-list assertions intentionally require a test update whenever the visible
  Telegram command menu changes.
- Hidden router commands are outside scope because they are not registered in the
  Telegram command menu.

## Verification

- `uv run pytest <startup-test-path> -q`: initially fails on `horizon_rx`, then
  passes after the production fix.
- `just check-fast`: exits successfully.
