# 2026-09-28-fix-manage-data-notification-html: Fix manage_data notification HTML injection and poison-pill queue handling

## Context

A `manage_data` notification for user 6587492495 (tx c791241a757d9da03b319196fad2589b7c4adaccfa17c8124d51c6ec9394b390, onym-audit binary data entries) got stuck as the Redis queue head since 2026-09-25: Telegram rejects the rendered HTML with `Bad Request: can't parse entities: Unclosed start tag at byte offset 289`, the coordinator treats any exception as transient and retries forever ("queue head retained"), blocking all later notifications for that user.

Root causes:
1. `decode_db_effect` injects blockchain-controlled `data_name`/`data_value` (and `operation.memo`) into parse-mode HTML without escaping.
2. `NotificationCoordinator._flush_owned` never drops a permanently-failing queue head (TelegramBadRequest = invalid payload, retries are useless).

## Files/Directories To Change

- `bot/infrastructure/utils/notification_utils.py`
- `bot/infrastructure/services/notification_coordinator.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `bot/tests/infrastructure/test_notification_coordinator.py`
- `docs/exec-plans/active/2026-09-28-2026-09-28-fix-manage-data-notification-html.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User (2026-09-28): "очередь сама разребется по обновлению. давай все три т.е. мемо тоже эканировать" — approved all three fixes (escape manage_data fields, escape memo, poison-pill queue head).

## Change Plan

1. [x] `bot/infrastructure/utils/notification_utils.py`: escape `data_name`/`data_value` in the three manage_data branches (set / removed / mention) with `html.escape`.
2. [x] `bot/infrastructure/utils/notification_utils.py`: escape `operation.memo` in the payment branch `memo_text`.
3. [x] `bot/infrastructure/services/notification_coordinator.py`: in `_flush_owned`, catch `TelegramBadRequest` from `send_notification` separately, log `notification_delivery_rejected`, drop the queue head via `acknowledge_if_lock_owned` (poison-pill), and continue with the next notification.
4. [x] Regression tests: escaped manage_data message rendering (binary value with `<` must not raise) in `bot/tests/infrastructure/test_notification_webhook.py`; poison-pill drop behavior in `bot/tests/infrastructure/test_notification_coordinator.py`.
5. [x] Run focused tests, `just lint`, `just arch-test`.

## Risks / Open Questions

- Poison-pill acks a notification that Telegram rejected: acceptable, because TelegramBadRequest is deterministic (payload invalid), retrying can never succeed. Timeout/other errors keep the queue-head-retained behavior.
- No data loss beyond the single malformed message: it was never deliverable.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_coordinator.py bot/tests/infrastructure/test_notification_webhook.py`
- `just lint`, `just arch-test`
- Expected: new tests pass; no regression in existing delivery-failure tests.
