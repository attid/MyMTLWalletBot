# delayed-blockchain-notifications: Отложенная доставка блокчейн-уведомлений

## Context

Blockchain-originated wallet notifications currently use the shared UI sender,
replace `last_message_id`, and can interrupt order, transfer, signing, and
settings flows. Add a durable sliding hold window, Redis-backed pending queue,
automatic delivery, and a non-navigating pending-notification badge without
delaying transaction-result screens that belong to the active user flow.

## Files/Directories To Change

- `bot/core/`
- `bot/infrastructure/services/`
- `bot/infrastructure/workers/`
- `bot/infrastructure/utils/telegram_utils.py`
- `bot/middleware/`
- `bot/routers/`
- `bot/start.py`
- `bot/other/config_reader.py`
- `bot/tests/`
- `shared/` (only if a cross-package Redis contract is required)
- `adr/`
- `docs/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++" in response to the explicit list of paths above.

## Change Plan

1. [x] Record the Redis queue, hold, delivery, locking, and UI separation design
   in `adr/` and relevant `docs/` pages.
2. [x] Add failing unit tests under `bot/tests/infrastructure/` for hold,
   enqueue/deduplication, flush, retries, locking, and expired delivery.
3. [x] Implement the notification model, Redis store, guard, independent
   Telegram delivery, coordinator, and worker under `bot/core/` and
   `bot/infrastructure/`.
4. [x] Add failing middleware/router tests under `bot/tests/routers/` using
   `mock_telegram` for sliding activity, terminal flow completion, and badge
   behavior without FSM or `last_message_id` mutation.
5. [x] Implement middleware registration, flow completion hooks, base-keyboard
   tracking, badge refresh/callback, configuration, and worker lifecycle in
   `bot/middleware/`, `bot/routers/`, `bot/start.py`, and
   `bot/other/config_reader.py`.
6. [x] Migrate blockchain notification delivery in
   `bot/infrastructure/services/notification_service.py` to the coordinator and
   remove its `last_message_id` mutation without changing transaction-result
   screens.
7. [x] Run focused tests, `just check-fast`, `just secret-scan`, and relevant
   external/smoke checks; fix only regressions caused by this task.
8. [x] Complete documentation and move this plan to `docs/exec-plans/completed/`.

### Expired-hold liveness repair (2026-07-11)

**Files/Directories To Change**

- `bot/infrastructure/services/notification_redis_store.py`
- `bot/infrastructure/services/notification_coordinator.py`
- `bot/tests/infrastructure/test_notification_redis_store.py`
- `bot/tests/infrastructure/test_notification_coordinator.py`
- `bot/tests/external/test_notification_redis_store_real.py`

**Edit Permission**

- [x] Allowed paths confirmed by user.
- [x] No edits outside the paths above (apart from this required execution-plan record).

Permission evidence:

> "Edit only notification store/coordinator unit/external tests as needed."

1. [x] Add deterministic failing store and coordinator interleaving tests, plus a real-Redis parity assertion, for an accept between final empty peek and expired-hold release.
2. [x] Atomically release only the expected hold while retaining an immediate due schedule when the pending queue is nonempty; retain renewed-hold fencing and the WATCH fallback parity.
3. [x] Run the requested focused, external, Ruff, mypy, and `just test-fast` verification commands without committing.

### Task3 review blockers (2026-07-11)

**Files/Directories To Change**

- `bot/infrastructure/services/notification_redis_store.py`
- `bot/infrastructure/workers/notification_delivery_worker.py`
- `bot/other/config_reader.py`
- `bot/start.py`
- `bot/infrastructure/services/app_context.py` (only if lifecycle ownership needs it)
- `bot/tests/infrastructure/test_notification_redis_store.py`
- `bot/tests/infrastructure/test_notification_delivery_worker.py`
- `bot/tests/external/test_notification_redis_store_real.py`
- `adr/0001-delayed-blockchain-notification-delivery.md`
- this execution plan

**Edit Permission**

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> "Edit store due query/tests, worker/config/start/app_context lifecycle/tests, and Markdown ADR/plan only to clarify heartbeat if needed."

1. [x] Add failing bounded-query and stale-prefix tests for Lua and WATCH due-user paths.
2. [x] Make due-user scans page-bounded at Redis while retaining stale cleanup and due-user liveness.
3. [x] Add failing finite poll-interval validation tests for settings and worker; implement validation.
4. [x] Add a failing lifecycle-order test; quiesce notification producers, await notification/background tasks, close notification Redis, then close the broker.
5. [x] Clarify the active flush-lock heartbeat lifetime in the ADR and verify all requested checks without committing.

**Verification (2026-07-11)**

- Focused notification tests: `79 passed, 2 deselected`.
- `just test-external`: passed, including real-Redis notification-store tests.
- `just test-fast`: `520 passed`.
- `just lint`: Ruff passed and configured core mypy reported no issues.
- A broader mypy invocation rooted at the touched modules reports 47 pre-existing
  errors in imported legacy modules; none are in the Task3 files.

### Final review fixes (2026-07-11)

**Files/Directories To Change**

- `bot/infrastructure/services/notification_service.py`
- `bot/infrastructure/services/notification_coordinator.py`
- `bot/infrastructure/services/notification_badge_service.py`
- `bot/infrastructure/utils/telegram_utils.py`
- `bot/middleware/notification_activity.py`
- `bot/routers/notification_settings.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `bot/tests/infrastructure/test_notification_coordinator.py`
- `bot/tests/infrastructure/test_notification_badge_service.py`
- `bot/tests/middleware/test_notification_activity.py`
- `bot/tests/routers/test_notification_settings.py`
- `adr/0001-delayed-blockchain-notification-delivery.md`
- this execution plan

**Edit Permission**

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> "Implement fixes for all final-review findings in the uncommitted delayed
> blockchain notification feature. You are authorized to edit only
> already-authorized bot code/test paths and existing task Markdown docs if needed."

1. [x] Add red regressions for webhook durable-accept failure, completion-lock
   contention, notification-settings activity/completion, post-send lease loss,
   and best-effort UI lock contention.
2. [x] Propagate durable acceptance failures while retaining expected filtering,
   and make flow completion retry the observed hold generation without releasing
   a renewed hold.
3. [x] Classify notification settings callbacks as flow activity and complete
   the flow after a successful filter save.
4. [x] Preserve at-least-once delivery after a successful Telegram send that
   loses its lease by attempting an acknowledgement-only recovery under a newly
   acquired lock; make normal UI rendering fall back without badge mutation when
   the badge lease is unavailable.
5. [x] Update the ADR delivery guarantee; run formatter, focused non-network
   tests, and lint. `just test-fast` and socket-backed router/webhook tests are
   blocked by the sandbox denying AF_INET socket creation.

### Final P1 follow-up (2026-07-11)

**Files/Directories To Change**

- `bot/middleware/notification_activity.py`
- `bot/tests/middleware/test_notification_activity.py`
- this execution plan

**Edit Permission**

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> "Fix the final P1 only, without commit: notification_activity.py callback
> classification misses the real create_filter_from: prefix used by
> notification_settings.py to enter filter configuration while FSM state is
> inactive. Use TDD... Do not modify unrelated files."

1. [x] Add a failing inactive-FSM callback-classification regression for
   `create_filter_from:`.
2. [x] Add the minimal callback prefix classification and run the requested
   formatter, focused tests, and lint without committing.

**Verification (2026-07-11)**

- Red: the focused classification test failed for
  `create_filter_from:abc123` before the prefix was added.
- Green: `bot/tests/middleware/test_notification_activity.py` passed
  (`33 passed`).
- `just fmt` and `just lint` passed with `UV_CACHE_DIR=/tmp/mmwb-uv-cache`.
- `bot/tests/routers/test_notification_settings.py` is blocked at its
  `mock_telegram` fixture because the sandbox denies AF_INET socket creation.

## Risks / Open Questions

- Redis queue acknowledgement must not remove an item before Telegram confirms
  delivery; per-user distributed locks must prevent concurrent flushes.
- Badge refresh is best-effort and must not block queue delivery when Telegram
  can no longer edit the current UI message.
- Base keyboards must be stored independently from FSM data and never include
  the derived badge row.
- The selected V1 design is a per-user Redis List with idempotency metadata and
  token-safe locks; Redis Streams remain an explicitly rejected alternative in
  ADR-0001.

## Verification

Final fresh verification on 2026-07-11:

- `just fmt` and `git diff --check`: passed.
- Focused socket-backed webhook/settings regressions: `3 passed`.
- Notification activity middleware: `33 passed`.
- `just check-fast`: passed; fast suite `550 passed`, Ruff, core mypy,
  architecture checks, docs contract, and execution-plan scope lock all passed.
- `just test-e2e-smoke`: `94 passed`.
- `just test-external`: `7 passed`, including real-Redis store and notifier flow.
- `just secret-scan`: passed; no leaks found.
- Independent Terra re-review findings were fixed, including the final
  `create_filter_from:` activity callback regression.
