# fix-stuck-notification-lock: Prevent immortal notification locks and blocked callbacks

## Context

Production logs show a `complete_flow` flush holding its Redis lease for more
than thirty minutes. The 90-second `asyncio.timeout` initiated Firebird
connection cancellation, but SQLAlchemy cleanup did not unwind, so the sibling
heartbeat kept renewing the lock forever and Telegram callbacks accumulated.

## Files/Directories To Change

- `bot/infrastructure/services/notification_coordinator.py`
- `bot/infrastructure/services/notification_redis_store.py`
- `bot/infrastructure/workers/notification_delivery_worker.py`
- `bot/infrastructure/workers/signing_worker.py`
- `bot/infrastructure/workers/sealedbox_worker.py`
- `bot/other/faststream_tools.py`
- `bot/middleware/notification_activity.py`
- `bot/tests/infrastructure/test_notification_coordinator.py`
- `bot/tests/infrastructure/test_notification_redis_store.py`
- `bot/tests/infrastructure/test_notification_delivery_worker.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `bot/tests/middleware/test_notification_activity.py`
- `bot/tests/test_signing_flow.py`
- `bot/tests/test_sealedbox_webapp_flow.py`
- `bot/tests/external/test_notification_redis_store_real.py`
- `docs/plans/2026-08-18-notification-lock-recovery-design.md`
- `docs/plans/2026-08-18-notification-lock-recovery.md`
- `adr/0002-worker-owned-notification-flow-completion.md`
- `docs/architecture.md`
- `docs/exec-plans/active/2026-08-18-fix-stuck-notification-lock.md`
- `docs/exec-plans/completed/2026-08-18-fix-stuck-notification-lock.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> давай чинить
>
> ++ (expanded permission for Redis store and delivery worker paths)
>
> ++ (expanded permission for signing, sealedbox, and WalletConnect background
> completion paths and their tests)

## Change Plan

1. [x] Add a RED regression test proving heartbeat renewal stops independently
       when a cancelled flush cannot unwind.
2. [x] Give the heartbeat its own monotonic ownership deadline.
3. [x] Preserve fenced acknowledgement for a late successful send while its
       original lease token remains valid.
4. [x] Add RED tests proving `complete_flow` only releases/reschedules durable
       work and never performs Telegram/Firebird delivery in the callback.
5. [x] Add a distinct Redis hold generation so same-second touches cannot be
       released by an older flow completion.
6. [x] Change `complete_flow` to hand delivery to the existing due-user worker.
7. [x] Fence Telegram completion to the generation captured at update entry and
       give background completion an explicit current-flow API.
8. [x] Isolate per-user worker flushes so one cancellation-resistant dependency
       cannot stop polling for every user.
9. [x] Update webhook integration coverage for worker-owned post-flow delivery.
10. [x] Record worker handoff, generation fencing, and independent heartbeat in
       an ADR.
11. [x] Run focused, external, and repository verification gates.

## Risks / Open Questions

- Delivery after flow completion moves from immediate inline execution to the
  next worker poll (normally within five seconds).
- The Redis queue remains durable and ordered; no new task-local queue is added.
- Balance-cache reset remains in the sender, but now runs outside the callback's
  DB session when queued work is released by the worker.

## Verification

- Focused notification, middleware, signing, and sealed-box suites: 201 passed.
- `just check-fast`: 421 passed; Ruff, mypy core, architecture, documentation,
  and scope-lock checks passed.
- `just test`: 762 passed, 8 deselected.
- `just test-external`: completed successfully; real Redis Lua store tests passed.
- Independent read-only review: READY with no remaining findings.
