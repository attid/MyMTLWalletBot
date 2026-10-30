# ADR-0001: Durable delayed delivery for blockchain notifications

- Status: Accepted
- Date: 2026-07-11
- Deciders: project owner and implementation agent

## Context

Blockchain-originated wallet notifications use the shared legacy notification
sender. Delivery clears and then replaces `last_message_id`, with the normal
notification settings and Return keyboard. Redis must delay delivery while a
user is active, but it must not introduce a second Telegram sender or change
the legacy notification UI semantics.

The system needs a sliding inactivity window, early release at logical flow
completion, automatic recovery after process restarts, safe operation with more
than one worker, ordered delivery, and a badge that does not alter FSM state or
tracked UI-message identity. User-initiated transaction result screens remain
part of the UI flow and are explicitly outside this notification pipeline.

## Decision

Use Redis directly as the source of truth for notification holds and pending
delivery. The design uses:

- `notification:hold:{user_id}`: absolute Unix timestamp with a bounded TTL;
- `notification:pending:{user_id}`: ordered Redis List of serialized
  `BlockchainNotification` values;
- `notification:dedupe:{user_id}`: Set of stable event idempotency keys;
- `notification:due`: Sorted Set mapping user IDs to the latest `hold_until`;
- `notification:flush_lock:{user_id}`: token-owned distributed lock with TTL;
- `notification:base_markup:{user_id}`: current base inline markup and tracked
  message ID, never including the derived badge row.

An atomic enqueue script combines deduplication and queue insertion. A single
polling worker per process selects due users from the Sorted Set; per-user locks
and a second hold check make multiple processes safe. `flush()` peeks the first
List item, calls `NotificationService`'s legacy `clear_last_message_id()` then
`cmd_info_message()` sender path, and removes that exact head only after
Telegram confirms success. A token-checking Lua script releases the lock. A
failed send leaves the item queued. The lock heartbeat exists only
for the lifetime of an active `flush()` lease, so a slow Telegram send cannot
expire that lease. It is not a per-user inactivity or action timer: `touch()`
only records the Redis hold and does not create an asyncio sleep or heartbeat
task.

If Telegram confirms a send after the worker has lost its lock lease, the worker
does not send again. It attempts an acknowledgement-only recovery under a new
lock and removes the exact queue head only if it owns that new lock. If recovery
cannot obtain a lock, the queued head remains for retry; this favours no loss
over an unavoidable duplicate when another worker may already have taken over.

Redis controls only scheduling and acknowledgement. `NotificationService` is
the single Telegram sender for both immediate acceptance and queued flushes;
it preserves legacy FSM/`last_message_id` handling and the notification
keyboard. A forbidden Telegram recipient is handled by marking the wallet for
deletion, and history is written only after Telegram accepts the send. Badge
refresh edits reply markup only and is best-effort; inability to edit an old
message never blocks delivery.

Activity middleware calls `touch()` for flow callbacks and messages handled in
an active FSM state, excluding the badge, `/start`, back/cancel, and terminal
callbacks. Logical flow endpoints call `complete_flow()`, which releases the
hold and flushes immediately.

## Amendment 2026-10-30: outbound chat speed

An incident on 2026-10-30 showed that durability and ordering were solved but
the outbound side was not: 3 246 maker fills of dust size produced one message
per fill (up to 93 fills per transaction), 273 messages reached one chat in four
minutes, Telegram answered with per-chat flood limits that escalated from 3 s to
2 430 s, and the inline retry middleware slept inside the delivery lock, so the
wait was both unbounded and forgotten after `delivery_timeout` cancelled it.

Decision, binding for this pipeline:

1. **One owner of outbound speed.** `NotificationCoordinator` owns it. The
   Telegram retry middleware must not sleep for this pipeline: it raises
   `ChatRateLimitedError` when the coordinator disables inline sleeping, and the
   coordinator persists `notification:cooldown:{user_id}` from `retry_after`
   (capped by configuration) and reschedules the user's due time.
2. **Pacing belongs to the same owner.** `notification:pace:{user_id}` allows at
   most one send per configured interval; pacing and cooldown are checked
   atomically by `reserve_send_slot` before every send.
3. **Badge edits share the chat budget.** A rate limit raised while refreshing
   the badge parks the chat exactly like a notification send does.
4. **Volume is bounded before delivery.** All maker fills of one transaction
   become one message: the first N fills plus the remaining count and a single
   `viewer.eurmtl.me/transaction/{hash}` link. The text budget is measured in
   visible characters (markup stripped), because Telegram counts rendered text.
5. **Filtering happens before bundling, and a trade filter may match either side
   of the fill** — the sold or the received asset — with the amount taken from
   the matched side.

Nothing is dropped to compensate for a slow chat: a parked chat keeps its queue
and delivers later. The compensating control is alerting on queue depth and head
age, not a drop policy.

## Consequences

- Positive: immediate and queued notifications have identical legacy UI
  behavior, including keyboard and `last_message_id` updates.
- Positive: pending notifications and deadlines survive bot restarts.
- Positive: ordered per-user delivery and distributed exclusion are explicit.
- Positive: the signing/WalletConnect FastStream path stays independent.
- Negative: Redis scripts and lock ownership add implementation complexity.
- Negative: an unbounded Telegram wait now becomes bounded delivery latency, so
  a parked chat may receive its backlog minutes later. This is preferred over
  silent loss or an escalating flood limit.
- Negative: Telegram cannot provide exactly-once delivery across a crash after
  send but before Redis acknowledgement, or a completed send whose recovery
  cannot reacquire the lock; rare duplicate delivery remains possible in those
  windows. Delivery is at-least-once, not exactly-once.
- Follow-up: operational metrics and dead-letter tooling may be added if retry
  volume justifies them; they are not required for the first implementation.

## Alternatives Considered

1. Redis Streams with consumer groups: stronger generic broker semantics, but
   unnecessary pending-entry and recovery complexity for ordered per-user
   `flush(user_id)` behavior.
2. One global Sorted Set with payload keys: scheduling is direct, but ordered
   partial acknowledgement per user is more complicated.
3. Per-action in-process timers: rejected because timers do not survive restart,
   multiply with activity, and do not coordinate across processes.
