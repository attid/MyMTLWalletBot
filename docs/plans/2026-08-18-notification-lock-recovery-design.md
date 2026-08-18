# Notification Lock Recovery Design

## Evidence

At `18:10:42`, a Telegram callback released its notification hold and entered
the synchronous `complete_flow` flush. At the 90-second ownership budget,
Firebird connection termination raised `CancelledError`, but coroutine cleanup
did not finish. The flush heartbeat was a sibling task cancelled only from the
unreached `finally`, so it continued renewing the 30-second Redis lease for more
than thirty minutes. Additional callbacks accumulated while unrelated users and
health probes continued normally.

## Design

`complete_flow` will remain an awaited API for all existing callers, but its
work becomes bounded Redis bookkeeping only. It observes the active hold and
atomically releases that generation. A separate monotonic Redis sequence gives
every touch a unique identity, including two touches in the same wall-clock
second. Telegram middleware captures that identity at update entry and resets
the task-local fence on exit. An activity touch atomically installs its new
generation in the same update task, so an older callback cannot release a hold
touched by a concurrent newer callback before the older handler completes.

Background result handlers already own and clear current FSM state, so they use
an explicitly named current-flow release rather than pretending to have a
per-operation generation token. The store reschedules a non-empty pending queue
at `now`, so the durable polling worker can acquire the delivery lock on a later
poll. Telegram and Firebird work therefore no longer run inside a user callback
or its middleware DB-session lifetime.

The delivery heartbeat receives a monotonic deadline equal to the coordinator's
lock ownership budget. It checks that deadline before every renewal and exits
when exhausted, setting `lease_lost`. Even if cancellation of the main flush
cannot unwind, the heartbeat can no longer renew forever; the Redis lease then
expires naturally within one lock TTL.

No detached delivery task is introduced. Queue durability, FIFO ordering,
deduplication, acknowledgement fencing, and worker retry semantics remain owned
by Redis and `NotificationDeliveryWorker`. The worker owns and tracks one task
per active user, bounded by its batch size. A poll waits at most one interval;
subsequent polls skip an already-active user and can service other due users.

When a send succeeds after the heartbeat deadline, the coordinator first tries
the original token's fenced acknowledgement. The token may still be valid for
up to one lock TTL after renewals stop. Only a failed original acknowledgement
triggers recovery under a newly acquired token, preventing an already-sent head
from remaining queued merely because the recovery lock is still occupied by
the original token.

## Verification

Tests prove the heartbeat renews at least once, sets lease loss at its deadline,
and stops renewing. Completion tests prove generation-fenced hold release occurs
without lock acquisition or sending. Redis tests cover same-second touches in
Lua and transaction fallbacks. Worker coverage proves a cancellation-resistant
user cannot block another due user or a later poll, while webhook integration
executes the worker-side delivery before asserting the Telegram result.
