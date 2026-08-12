# bot-pool-hang-recovery: Prevent bot hangs from exhausted DB pool

## Context

Production log `localdoc/mmwb_bot.1-2026-07-23T22-02-22.zip` shows DB
connections accumulating until the pool reached `10/10`. Telegram update
handlers then waited for a connection, and `cmd_send_message_1m` remained
running forever because its timeout only logged warnings. Redis-backed jobs
continued, confirming pool exhaustion rather than a stopped event loop.

## Files/Directories To Change

- `bot/middleware/db.py`
- `bot/infrastructure/utils/async_utils.py`
- `bot/infrastructure/workers/message_worker.py`
- `bot/db/db_pool.py`
- `bot/infrastructure/services/bot_health_service.py`
- `bot/tests/middleware/`
- `bot/tests/infrastructure/`
- `docs/plans/2026-07-23-bot-pool-hang-recovery-design.md`
- `docs/plans/2026-07-23-bot-pool-hang-recovery.md`
- `docs/exec-plans/active/2026-07-23-bot-pool-hang-recovery.md`
- `docs/exec-plans/completed/2026-07-23-bot-pool-hang-recovery.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> The assistant listed the production paths and test directories, and the user
> replied `ок давай`. Execution-plan and design Markdown are allowed by the
> repository intake protocol.

## Change Plan

1. [x] Remove the global Telegram-handler deadline so legitimate rate-limit
       retries and bulk operations are never cancelled.
2. [x] Keep DB checkout ownership context in `DbSessionMiddleware` without
       changing handler lifetime.
3. [x] Add RED regression tests proving long Telegram retries are not cancelled.
4. [x] Preserve warning-only task monitoring for retry-safe bulk delivery.
5. [x] Add RED tests proving the message worker does not hold a DB session
       during Telegram/FSM I/O.
6. [x] Split worker reads and status writes into short DB sessions.
7. [x] Track long-lived pool checkouts with task and Telegram-update ownership;
       retain the existing timed DB probe as the health signal.
8. [x] Treat a currently running long scheduler job as healthy when the bounded
       DB probe succeeds.
9. [x] Run focused regression tests and `just check-fast`.
10. [x] Move this completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- Telegram rate-limit retries can legitimately take several minutes and must
  never be cancelled by a generic handler/worker deadline.
- Worker delivery remains at-least-once: a crash after Telegram accepts a
  message but before `mark_sent` can produce a retry, matching existing
  semantics.
- A long-running active worker is not proof of a hang when the DB probe still
  succeeds.

## Verification

- `uv run pytest bot/tests/middleware/test_db.py -q`
- `uv run pytest bot/tests/infrastructure/test_async_utils.py -q`
- `uv run pytest bot/tests/infrastructure/test_message_worker.py -q`
- `uv run pytest bot/tests/infrastructure/test_bot_health_service.py -q`
- `just check-fast`
- Expected: long tasks are warned about but continue, worker network waits occur
  without a checked-out DB session, healthy long-running delivery stays green,
  and long checkouts identify their task/update owner.
