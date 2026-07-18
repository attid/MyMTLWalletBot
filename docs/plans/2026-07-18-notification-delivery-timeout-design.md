# Bounded Notification Delivery Design

## Problem

A notification flush owns a token-scoped Redis lock and renews it while sending
through Telegram. Production logs show that an awaited sender can remain stuck
for more than 25 minutes. The heartbeat therefore keeps the lock alive, the due
worker logs contention every five seconds, queued notifications cannot advance,
and a terminal Telegram handler can retain its database session indefinitely.

Separately, badge refresh treats Telegram's idempotent `message is not modified`
response as an error even though notification delivery is subsequently
acknowledged.

## Decision

Bound every `NotificationSender.send_notification()` call inside
`NotificationCoordinator` to 30 seconds. A timeout cancels the in-flight sender,
does not acknowledge the queue head, exits the owned flush, cancels its heartbeat,
and releases the token-owned lock in the existing `finally` path. The durable due
entry then permits the worker to retry. This keeps ADR-0001's at-least-once
contract: a rare duplicate remains possible when Telegram accepted a request but
its response was lost, while notification loss is avoided.

The timeout is injected into the coordinator with a 30-second default so tests
can use a short deterministic value. It does not modify the global Telegram
session or retry middleware.

Coordinator messages will contain operational identifiers in their rendered
text as well as bound fields: `user_id`, `notification_id`, `reason`, timeout,
and lock-release outcome. This makes the current plain Loguru sink actionable.

Badge refresh will recognize only Telegram's exact `message is not modified`
`TelegramBadRequest` as a successful no-op and emit a debug diagnostic. Other
Telegram bad requests and unexpected errors remain error-level failures.

## Verification

Tests reproduce a never-returning sender and confirm cancellation, retained queue
head, and lock release. A separate test raises Telegram's identical-markup error
and confirms a no-op diagnostic without an error record. Existing concurrency,
lease-loss, ordering, and badge tests remain unchanged.
