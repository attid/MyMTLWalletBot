# flowback-none-fallback: Fix FlowBack fallback after QR confirmation

## Context

Production callback `FlowBack` failed after a QR-driven payment confirmation because
the amount-screen text was absent and reached aiogram as `SendMessage(text=None)`.

## Files/Directories To Change

- `bot/routers/send.py`
- `bot/infrastructure/utils/telegram_utils.py`
- `bot/tests/routers/test_send.py`
- `bot/tests/infrastructure/test_telegram_utils.py`
- `.gitignore`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Reproduce the QR-confirmation `FlowBack` failure in a router regression test.
2. [x] Restore the amount screen only when its saved text is valid; otherwise return
   to the safe address-entry screen while preserving existing valid FlowBack behavior.
3. [x] Guarantee the Telegram UI sender rejects missing text before constructing an
   aiogram request and cover the invariant with an infrastructure test.
4. [x] Verify callback acknowledgement and the edit-failure-to-send fallback path.
5. [x] Ignore local `.claude/` state without modifying its contents.
6. [x] Run targeted tests, `just check-fast`, and `just check`.

## Risks / Open Questions

- The QR path has no amount prompt to restore, so its safe previous screen is address
  entry rather than a fabricated amount prompt.
- Existing FlowBack paths with a stored amount prompt must remain byte-for-byte
  unchanged at the user-facing boundary.

## Verification

- `uv run --package mmwb-bot pytest bot/tests/routers/test_send.py bot/tests/infrastructure/test_telegram_utils.py`
- `just check-fast`
- `just check`
- The regression receives a valid fallback message and `answerCallbackQuery`; all
  repository gates pass.
