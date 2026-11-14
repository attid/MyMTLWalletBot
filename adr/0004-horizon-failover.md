# ADR-0004: Automatic Horizon failover instead of manual `/horizon`

- Status: Accepted
- Date: 2026-11-13
- Deciders: project owner and implementation agent

## Context

The bot switched Horizon endpoints by hand with `/horizon` and `/horizon_rw`,
rotating a hardcoded list in `bot/other/config_reader.py`. Two problems:

1. The switch did not switch most traffic. `StellarService` captured
   `config.horizon_url` at construction (`start.py`), and
   `AnchorDiscoveryService` captured it at import time
   (`bot/routers/assets.py`), while `bot/other/stellar_tools.py` re-read config
   per call. The process therefore talked to two different Horizon nodes at
   once, with diverging sequence numbers and offers.
2. Nobody was told about a failing node. On 2026-09-05
   `https://horizon.stellar.org` returned 429 and a dependent service went into
   a restart loop; the bot had no automatic escape and no alert.

## Decision

- Endpoints come from a required `HORIZON_URLS` config value (comma separated,
  priority order, primary first, `|ro` suffix marks a read-only node). There is
  no hardcoded fallback: a missing value fails startup.
- `infrastructure/services/horizon_pool.py` owns a per-process pool for reads
  (`ro`) and submissions (`rw`): one attempt per endpoint, at most three
  attempts, 25s budget, `request_timeout=8`/`post_timeout=15`.
- Failover triggers only on transport errors/timeouts, HTTP 5xx and HTTP 429.
  Business errors (400/404: `tx_bad_seq`, `op_underfunded`, unknown account)
  never switch endpoints.
- Cooldowns: 429 starts at 60s, transport/5xx at 30s, doubling per consecutive
  failure up to 600s, reset by success. A 60s sticky window plus a
  "more than 5 switches in 10 minutes" freeze prevent flapping. When every
  endpoint is down the call fails fast and the all-down backoff escalates
  1s -> 5s -> 15s -> 60s across calls; that window never outlives the node
  cooldowns, so a recovered endpoint is probed immediately.
- Pool state is in memory only. Restart forgets cooldowns and starts from
  primary.
- Every component resolves the URL per call (pool or an explicit test pin);
  nothing stores it. A guard test enforces this.
- Manual commands are removed: the admin can only change the endpoint list in
  config and restart. Nobody re-adds a "convenient button" by accident.
- Admin gets three notifications via `bot.send_message` (best effort, no queue):
  switch, all-down/freeze, recovery. Structured `event=horizon_failover` logs
  carry the details.

## Consequences

- A dead or rate-limited node costs at most one attempt plus a 60s cooldown;
  users see the secondary node instead of an error.
- Worst-case latency for one call with dead nodes is bounded by the 25s budget.
- No escape hatch exists beyond editing config and restarting; accepted because
  a manual rotation was exactly the mechanism that silently diverged traffic.
- `HORIZON_URL`/`HORIZON_URL_RW` are gone from code, compose and template, so a
  deployment that still sets only those variables fails loudly at startup
  instead of running half-configured.
