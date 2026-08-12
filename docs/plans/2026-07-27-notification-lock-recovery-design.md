# Notification Lock Recovery Design

## Problem

`localdoc/log27.log` records a successful WalletConnect signing flow for user
`7394698`, followed by four durably queued blockchain notifications. A terminal
callback released the notification hold, but the resulting flush kept renewing
its per-user delivery lock for more than fifteen minutes. Later callbacks and
`/start` requests accumulated and retained DB sessions.

Two defects are in scope:

1. `do_wc_sign_and_respond()` renders a terminal success screen without calling
   `complete_notification_flow()`.
2. `NotificationCoordinator` bounds an individual sender call but has no
   absolute bound on the lifetime of the owned delivery-lock operation. Badge
   refresh also runs while that delivery lock is owned even though the badge is
   derived, best-effort UI state.

## Decision

Keep ordinary Telegram handlers and bulk delivery warning-only. Add a separate
finite ownership budget only to durable blockchain-notification flushes.
`NotificationCoordinator._flush_with_owned_lock()` will stop a flush that
exceeds that budget and will always cancel its heartbeat and token-release the
lock in `finally`.

The pending Redis queue remains authoritative. Items are removed only by the
existing token-checked acknowledgement after a successful sender return. If the
ownership budget expires first, an unacknowledged item remains queued for a
later retry. This preserves the established at-least-once contract: rare
duplicates remain possible in the unavoidable Telegram-accepted/Redis-not-yet-
acknowledged window, but notification loss is not introduced.

Badge refresh will no longer occur between acknowledgement and delivery-lock
release. The flush records whether queue state changed, releases the delivery
lock, and then performs one bounded best-effort refresh. A stuck or stale
Telegram markup edit therefore cannot retain the delivery lock.

WalletConnect success will render its existing success screen and then call
`complete_notification_flow()`. Error paths remain unchanged.

## Observability

Structured debug records will identify flush stages (`send`, `ack`, `badge`)
with `user_id`, `reason`, and notification ID where available. A lock-lifetime
timeout gets a dedicated warning event. Release logging remains in `finally`.

## Testing

Regression tests simulate:

- a WalletConnect success and assert terminal flow completion;
- an await that never completes while the lock ownership budget expires;
- a badge refresher that never completes and verify the delivery lock has
  already been released;
- queue acknowledgement and FIFO behavior after moving badge refresh.

Focused tests run before the repository-wide fast and full gates.
