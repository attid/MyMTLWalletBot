# notification-delivery-timeout: Bound notification delivery and improve diagnostics

## Context

Production logs on 2026-07-18 show a queued notification flush retaining its
renewable Redis lock for more than 25 minutes after `complete_flow()`. The
delivery coroutine never logs success or failure, the polling worker retries
every five seconds, and Telegram handlers retain database sessions while
awaiting completion. Badge refreshes also log Telegram's harmless
`message is not modified` response as an error with a traceback.

## Files/Directories To Change

- `bot/infrastructure/services/notification_coordinator.py`
- `bot/infrastructure/services/notification_badge_service.py`
- `bot/tests/infrastructure/test_notification_coordinator.py`
- `bot/tests/infrastructure/test_notification_badge_service.py`
- `docs/exec-plans/active/2026-07-18-notification-delivery-timeout.md`
- `docs/plans/2026-07-18-notification-delivery-timeout-design.md`
- `docs/plans/2026-07-18-notification-delivery-timeout-implementation.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++"

## Change Plan

1. [x] Add a failing coordinator regression proving a stuck sender is cancelled,
   its queue head remains pending, and the flush lock is released.
2. [x] Bound each notification sender call to 30 seconds while preserving
   at-least-once queue semantics.
3. [x] Add a failing badge regression proving Telegram's `message is not
   modified` response is recorded as a harmless no-op rather than an error.
4. [x] Include operational identifiers directly in coordinator log messages
   because the current text formatter omits bound structured fields.
5. [x] Run focused tests, full tests, repository gates, and move this plan to
   completed.

## Risks / Open Questions

- Cancelling an ambiguous Telegram request can produce an at-least-once retry
  duplicate if Telegram accepted the send but the response never arrived. This
  is consistent with ADR-0001's existing delivery guarantee and favours no loss.
- A timeout must retain the exact queue head and release only the current token's
  lock.
- The timeout is local to blockchain notification delivery and must not alter
  global Telegram retry behaviour.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_coordinator.py -q`
- `uv run pytest bot/tests/infrastructure/test_notification_badge_service.py -q`
- `just test`
- `just check-fast`
- `git diff --check`
- Expected: a blocked sender is cancelled within the configured test timeout,
  is not acknowledged, and releases its lock; identical badge markup produces
  no error-level record.

Verification evidence:

- RED timeout/no-op: two focused tests failed because the coordinator rejected
  no timeout argument and badge idempotency emitted `notification_badge_edit_failed`.
- RED diagnostics: timeout emitted no event and contention text omitted
  `user_id`/`reason`.
- RED validation: zero, negative, infinite, and NaN timeouts were accepted.
- GREEN focused infrastructure suites: `42 passed`.
- Full test suite: `860 passed, 7 deselected`.
- `just check-fast`: Ruff and mypy passed, `552 passed`, architecture and docs
  checks passed.
- `git diff --check`: passed.
