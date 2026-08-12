# bot-functional-healthcheck: Add functional bot container healthcheck

## Context

On 2026-07-23 the bot process and event loop stayed alive while commands stopped
receiving responses. Database-backed jobs accumulated and `cmd_send_message_1m`
stopped completing, so a process-only healthcheck would not detect the outage.

## Files/Directories To Change

- `Dockerfile`
- `bot/infrastructure/services/bot_health_service.py`
- `bot/infrastructure/services/app_context.py`
- `bot/infrastructure/services/notification_service.py`
- `bot/infrastructure/workers/message_worker.py`
- `bot/start.py`
- `bot/tests/infrastructure/test_bot_health_service.py`
- `bot/tests/infrastructure/test_message_worker.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `docs/exec-plans/active/2026-07-23-bot-functional-healthcheck.md`
- `docs/exec-plans/completed/2026-07-23-bot-functional-healthcheck.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User replied `++` after the production paths and
> `bot/tests/infrastructure/` were proposed. Execution-plan Markdown is allowed
> by the repository intake protocol.

## Change Plan

1. [x] Add failing tests for scheduler staleness and bounded database probing.
2. [x] Implement a health service with startup grace, scheduler heartbeat, and
       a timed Firebird probe.
3. [x] Add failing tests for worker heartbeat integration and HTTP status.
4. [x] Expose `GET /health` from the bot webhook server and wire the health
       service through `AppContext`.
5. [x] Add a functional container `HEALTHCHECK`.
6. [x] Run focused tests and `just check-fast`.
7. [x] Move this completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- A healthcheck must not restart an idle but healthy bot during startup; use a
  start period and matching in-process startup grace.
- Telegram itself is intentionally excluded from the probe to avoid restart
  loops during an upstream Telegram outage.
- The configured webhook port is 8081 and the container healthcheck targets the
  loopback endpoint on that port.

## Verification

- `uv run pytest bot/tests/infrastructure/test_bot_health_service.py -q`
- `uv run pytest bot/tests/infrastructure/test_message_worker.py -q`
- `uv run pytest bot/tests/infrastructure/test_notification_webhook.py -q`
- `just check-fast`
- Expected: all checks pass; stale scheduler and DB timeout reports return
  unhealthy, while current heartbeat plus a successful DB probe returns healthy.
