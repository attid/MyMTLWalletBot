# swap-sign-msg: Add swap signing context

## Context

Swap confirmation already stores XDR and uses the shared signing flow after the
user presses Yes. Add the same signing context used by send/SEP flows so PIN,
password, no-password, and WebApp signing screens explain that the user is
signing a swap.

## Files/Directories To Change

- `bot/routers/swap.py`
- `bot/langs/*.json`
- `bot/tests/routers/test_swap.py`
- `docs/exec-plans/active/2026-05-23-swap-sign-msg.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add localized `sign_swap_msg` text.
2. [x] Store `sign_msg` with swap XDR for text command, strict-send menu flow,
   and strict-receive menu flow.
3. [x] Add/update swap router tests for `sign_msg`.
4. [x] Run focused swap tests and `just check-fast`.

## Risks / Open Questions

- Keep confirmation text unchanged; only the later signing screen should get the
  extra context.
- Existing Decode/WebApp signing behavior should be reused without extra routes.

## Verification

- `uv run pytest bot/tests/routers/test_swap.py`
- `uv run pytest bot/tests/other/test_langs_json.py`
- `just check-fast`
- `git diff --check`
