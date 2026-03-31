# telegram-forbidden-wallet-delete: Mark wallet deleted on TelegramForbiddenError

## Context

Why this task exists and links to issue/ADR.

## Files/Directories To Change

- `bot/infrastructure/services/notification_service.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `docs/exec-plans/active/2026-03-31-telegram-forbidden-wallet-delete.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add a failing test in `bot/tests/infrastructure/test_notification_webhook.py` for `TelegramForbiddenError` during notification delivery.
2. [x] Update `bot/infrastructure/services/notification_service.py` to mark the wallet as deleted and commit within the same session block when Telegram reports the bot was blocked.
3. [x] Keep non-forbidden send failures on the existing logging path.
4. [x] Re-run the targeted notification webhook tests.
5. [x] Update the plan status and verification notes.

## Risks / Open Questions

- Marking only the current wallet as deleted assumes wallet-level suppression is the intended granularity.
- The mocked DB session in tests must assert `commit()` to match repo rules.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_webhook.py -q`
- The new forbidden-user test fails before the fix, then passes after the fix.
- Final result: `8 passed in 1.99s`.
