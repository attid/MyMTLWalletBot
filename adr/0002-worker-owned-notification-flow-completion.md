# ADR-0002: Worker-owned delivery after notification flow completion

- Status: Accepted
- Date: 2026-08-18
- Deciders: project owner and implementation agent
- Supersedes: ADR-0001 only where it requires `complete_flow()` to flush inline

## Context

ADR-0001 made logical flow completion release the activity hold and flush the
pending notification queue immediately. Production showed that this couples a
Telegram callback and its DB-session lifetime to notification delivery. A
Firebird connection cancellation failed to unwind after the coordinator's
ownership timeout, while the independent heartbeat continued renewing the
Redis lock for more than thirty minutes. User callbacks accumulated even though
the process, worker polling, and unrelated users remained responsive.

An `asyncio.timeout` is cooperative: it cannot guarantee that driver cleanup
honours cancellation. Lock safety therefore cannot depend on the main flush
coroutine reaching its `finally` block.

## Decision

`complete_flow()` atomically releases only the hold generation it observed.
Every `touch()` allocates a distinct, monotonically increasing Redis generation;
the deadline alone is not used as an identity because two touches can occur in
the same second. Telegram middleware captures the current generation at update
entry, and an activity touch atomically replaces that task-local fence with the
new generation. A terminal handler can release only its captured generation,
even if a concurrent newer update touches before the older handler completes.
The task-local value is reset when middleware exits.

Background signing, sealed-box, and WalletConnect results already complete and
clear the user's current FSM state. They therefore use a separately named
current-flow completion API that intentionally snapshots and releases the
current hold. Strict per-operation background fencing would also require the
FSM cleanup and durable worker payloads to carry the same operation token.

The release operation keeps a non-empty pending queue scheduled at the current
time. `NotificationDeliveryWorker` performs the resulting flush on a later
poll; logical flow callbacks never perform Telegram or Firebird notification
delivery inline.

Each flush heartbeat also receives its own monotonic ownership deadline. It
stops renewing and marks the lease lost when that deadline is reached,
independently of whether cancellation of the main flush coroutine completes.
The Redis lock can then expire within its configured TTL.

The worker runs due-user flushes in separately tracked tasks. It waits no more
than one poll interval for a batch and skips users that already have an active
flush. The number of active tasks is bounded by the configured batch size, so
one cancellation-resistant dependency cannot stop later polls or unrelated
users. After a late successful send, the coordinator first attempts fenced
acknowledgement with the original token; recovery with a new token is attempted
only when the original fenced acknowledgement fails.

Immediate notification acceptance without an active hold continues to attempt
delivery directly. Manual badge delivery retains its explicit flush behavior.

## Consequences

- Positive: flow completion has bounded Redis-only work and does not reserve a
  callback DB session during notification delivery.
- Positive: a cancellation-resistant driver cleanup cannot create an immortal
  notification lock.
- Positive: durable FIFO, deduplication, acknowledgement fencing, and retry
  behavior remain unchanged.
- Positive: same-second activity cannot be mistaken for the flow generation
  being completed.
- Positive: an older Telegram update cannot release a generation touched by a
  newer concurrent update after the older update entered middleware.
- Positive: one stuck user does not block delivery polling for all users.
- Negative: a queued notification is delivered on the next worker poll rather
  than inside the terminal callback, normally adding up to one poll interval.
- Negative: the worker can retain a stuck per-user task until its dependency
  unwinds; tracked tasks are bounded by the delivery batch size.
- Negative: an immediate-accept or manual flush coroutine may still remain
  stuck in a cancellation-resistant dependency, but its Redis lease renewal is
  bounded and it does not block logical flow completion.
- Follow-up: add operational metrics for heartbeat deadline exhaustion if log
  frequency justifies dedicated alerting.

## Alternatives Considered

1. Fire-and-forget delivery from `complete_flow()`: rejected because task
   ownership, shutdown, and exception handling would become process-local.
2. Force-cancel the Firebird executor call: rejected because Python cannot
   safely terminate a running synchronous driver function.
3. Keep inline delivery and only shorten timeouts: rejected because cooperative
   cancellation cannot enforce a hard lifetime.

## Redis Keys Added

- `notification:hold_generation:<user_id>`: current per-user generation, with
  the same TTL as its hold.
- `notification:hold_generation_sequence`: persistent monotonic allocator for
  generation identities within the configured key prefix.
