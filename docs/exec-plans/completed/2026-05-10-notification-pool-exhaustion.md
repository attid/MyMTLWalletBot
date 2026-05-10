# notification-pool-exhaustion: Notification pool exhaustion fix

## Context

Production log `localdoc/mmwb_bot.1.x81y102qq4fab1szlpsidwtvz-2026-05-10T11-49-27.log`
shows a notification storm around 2026-05-09 04:05:17 where SQLAlchemy reaches
`QueuePool limit of size 20 overflow 50`. Stack traces point at webhook
notification handling and the message worker competing for DB connections.
`NotificationService.process_notification()` currently holds a DB session while
sending notifications and then opens nested DB sessions per recipient.

## Files/Directories To Change

- `bot/infrastructure/services/notification_service.py`
- `bot/infrastructure/persistence/sqlalchemy_wallet_repository.py`
- `bot/core/interfaces/repositories.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `bot/tests/infrastructure/test_infrastructure_repositories.py`
- `docs/exec-plans/completed/2026-05-10-notification-pool-exhaustion.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> Implement the plan.

## Change Plan

1. [x] Add RED tests for bounded webhook concurrency and notification DB session lifetime.
2. [x] Add RED tests for direct wallet cache reset without read-before-write.
3. [x] Add a notification-processing semaphore in `NotificationService`.
4. [x] Snapshot wallet rows inside short DB sessions before sending notifications.
5. [x] Batch-load notification filters and avoid per-recipient filter sessions.
6. [x] Reset balance cache with a direct short update by wallet id.
7. [x] Run focused tests and repo gates.

## Risks / Open Questions

- Existing unrelated worktree changes must not be reverted.
- Semaphore protects the DB pool but may slightly delay webhook responses during bursts.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_webhook.py -q`
- `uv run pytest bot/tests/infrastructure/test_infrastructure_repositories.py -q`
- `just lint`
- `just test-fast`
- `just arch-test`
