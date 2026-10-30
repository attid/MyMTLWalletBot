# Runbook: notification flood / Telegram rate limit

Use when users report a burst of blockchain notifications, notifications stop
arriving, or logs show `failed due to rate limit` / `notification_chat_parked`.

## Symptoms in order of appearance

1. One chat receives many messages for one transaction, or for a stream of dust
   fills of a resting offer (`trade` events).
2. Logs: `notification_chat_parked`, `notification_chat_cooldown_started` with a
   growing `retry_after` (3 s → 279 s → 1 599 s → 2 430 s).
3. Logs: `failed due to rate limit` from the Telegram retry middleware, then
   `notification_flush_timed_out`, `queue head retained`.
4. Other chats are unaffected — the limit is per chat.

## First checks (read-only, 2 minutes)

1. Queue and cooldown for the affected user:
   `redis-cli LLEN notification:pending:<user_id>`
   `redis-cli GET notification:cooldown:<user_id>`
   `redis-cli GET notification:pace:<user_id>`
2. Accepted events survive 30 days in `notification:dedupe:<user_id>`
   (`SCARD` for volume, members look like `txhash:event_type:event_index:user_id`).
3. Delivered count and pace:
   `grep -c "delivered and acknowledged" logs/mmwb*.log`,
   `grep "delivered and acknowledged" logs/mmwb*.log | cut -c1-16 | uniq -c`.
4. Rate-limit ladder:
   `grep "failed due to rate limit" logs/mmwb*.log | sed -E 's/.*Sleeping ([0-9]+).*/\1/' | sort -n | uniq -c`

## What to do

1. Do **not** restart the container. The flood window lives on the Telegram side
   and the queue lives in Redis; a restart re-hammers the same chat.
2. Let the cooldown expire: the chat is parked until `notification:cooldown`,
   and the queue is preserved by design.
3. If the volume is still growing (an attacker filling resting offers in dust
   sizes), reduce the source: ask the owner of the affected wallet whether to
   create a `trade` filter from Bot → Notification settings → «Фильтр по
   трейдам» (works without history, matches either side of the fill).
4. If a single transaction produced hundreds of messages, bundling is not
   working as configured — check `notification_bundle_max_lines`.

## What not to do

1. Do not delete `notification:pending:*` keys to "clear the noise": that is
   silent notification loss.
2. Do not lower `notification_chat_cooldown_max_seconds` to make the bot retry
   sooner; that renews the flood window.
3. Do not disable `notification:pace:*`; pacing is the reason 429 does not
   escalate.

## After the incident

1. Record the shape: fills per transaction, messages per minute, retry ladder.
2. Add a regression test with that payload shape if the case is new.
