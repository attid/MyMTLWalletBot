# notification-watchdog: Alert admins when webhooks are silent for an hour

## Context

Webhook notifications are handled in-memory by `NotificationService`, but there
is no runtime signal when the stream goes silent. Add an in-memory watchdog
that alerts all admins once per hour of silence while the service is running.

## Files/Directories To Change

- `bot/infrastructure/services/notification_service.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `docs/exec-plans/active/2026-03-26-notification-watchdog.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> +

## Change Plan

1. [x] Add failing tests for silence watchdog alerts and timer reset behavior.
2. [x] Add in-memory watchdog state and admin alert helpers to `NotificationService`.
3. [x] Start and stop the watchdog with the service lifecycle.
4. [x] Update notification processing so real notifications reset the silence timer.
5. [x] Run targeted webhook/watchdog tests.

## Risks / Open Questions

- Watchdog must not spam admins more often than once per hour of silence.
- Service restarts should not backfill historical silence; monitoring starts from current process lifetime.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_webhook.py -q`
- `just lint`
- Expected signals: new watchdog regression tests fail before implementation and pass after the service adds silence monitoring.
