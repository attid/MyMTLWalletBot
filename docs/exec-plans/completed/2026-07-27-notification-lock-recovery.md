# notification-lock-recovery: Bound notification lock lifetime and complete WalletConnect flows

## Context

Production log `localdoc/log27.log` shows a WalletConnect user accumulating
four delayed notifications while a live notification flush lock remained owned
for more than fifteen minutes. The lock heartbeat kept renewing the lease, the
flush never logged delivery timeout/release, and later Home and `/start`
handlers accumulated while retaining DB sessions. The WalletConnect success
callback also does not currently complete its notification flow.

## Files/Directories To Change

- `bot/other/faststream_tools.py`
- `bot/infrastructure/services/notification_coordinator.py`
- `bot/tests/test_signing_flow.py`
- `bot/tests/infrastructure/test_notification_coordinator.py`
- `docs/plans/2026-07-27-notification-lock-recovery-design.md`
- `docs/plans/2026-07-27-notification-lock-recovery.md`
- `docs/exec-plans/active/2026-07-27-notification-lock-recovery.md`
- `docs/exec-plans/completed/2026-07-27-notification-lock-recovery.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> The assistant listed the two production files, two test files, and Markdown
> plans, then asked for permission. The user replied `++`.

## Change Plan

1. [x] Add RED tests proving WalletConnect success completes the notification
       flow.
2. [x] Add RED tests proving a stuck flush cannot renew its delivery lock
       forever and that unbounded badge refresh cannot retain that lock.
3. [x] Complete the WalletConnect flow after the success screen is rendered.
4. [x] Bound notification lock ownership without adding a global Telegram
       handler timeout or changing bulk-send retry behavior.
5. [x] Acknowledge FIFO delivery under the lock, then refresh the best-effort
       badge outside the delivery lock with its own bound.
6. [x] Add structured stage and timeout logs with user, reason, and notification
       identifiers.
7. [x] Run focused tests, `just check-fast`, and the full test suite.
8. [x] Move the completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- Telegram cannot guarantee exactly-once delivery if a bounded flush is
  interrupted after Telegram accepts a message but before Redis acknowledgement;
  the existing at-least-once contract prefers a possible duplicate over loss.
- The bound applies only to durable blockchain notification flushes. It must not
  cancel ordinary Telegram handlers, dividend broadcasts, or other bulk sends.
- Badge refresh is derived UI state and may lag after a timeout; the pending
  Redis queue remains authoritative.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_coordinator.py -q`
- `uv run pytest bot/tests/test_signing_flow.py -q`
- `just check-fast`
- `just test`
- Expected: WalletConnect success completes the hold, a simulated stuck flush
  releases its token-owned lock while retaining unacknowledged queue entries,
  and a stuck badge cannot hold the delivery lock.

Results:

- RED: the three new regression scenarios failed on the previous behavior.
- Focused affected files: `70 passed`.
- `just check-fast`: `586 passed`; Ruff, mypy, import boundaries, docs contract,
  and execution-plan scope checks passed.
- `just test`: `896 passed, 7 deselected`.
- `git diff --check`: passed.
