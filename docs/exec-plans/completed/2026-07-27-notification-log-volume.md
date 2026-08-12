# notification-log-volume: Reduce notification hot-path log volume

## Context

Production log `localdoc/log28.log` contains 1,996 lines during a normal
12-second notification burst. The per-stage diagnostic added in commit
`9468a9c` accounts for 942 lines and the badge-start diagnostic for another
121. The burst delivered notifications successfully, but synchronous log
volume contributed avoidable load on the bot hot path.

## Files/Directories To Change

- `bot/infrastructure/services/notification_coordinator.py`
- `bot/tests/infrastructure/test_notification_coordinator.py`
- `docs/exec-plans/active/2026-07-27-notification-log-volume.md`
- `docs/exec-plans/completed/2026-07-27-notification-log-volume.md`
- `docs/plans/2026-07-27-notification-log-volume.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> The assistant listed the coordinator, its test file, and Markdown execution
> plan paths. The user replied `++`.

## Change Plan

1. [x] Add a RED test proving a successful flush does not emit per-stage or
       badge-start diagnostics.
2. [x] Remove success-path logging while retaining the in-memory stage used by
       timeout diagnostics.
3. [x] Include timeout context in the rendered warning message because the
       production text sink does not render structured extras.
4. [x] Run focused tests, `just check-fast`, and `just test`.
5. [x] Move this completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- Timeout/error warnings must remain actionable after hot-path logs are
  removed.
- Notification delivery, locking, retry, and timeout behavior must not change.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_coordinator.py -q`
- `just check-fast`
- `just test`
- Expected: no `notification_flush_stage` or
  `notification_badge_refresh_stage` records on success; timeout warning
  contains user, reason, stage, notification ID, and timeout.

Results:

- RED: both logging regressions failed against the previous behavior.
- Coordinator suite: `42 passed`.
- `just check-fast`: `587 passed`; Ruff, mypy, import boundaries, docs contract,
  and execution-plan scope checks passed.
- `just test`: `897 passed, 7 deselected`.
