# Architecture

## Monorepo Context

This repository is a uv workspace with three packages:

- `bot/`: Telegram bot application.
- `webapp/`: FastAPI signing webapp.
- `shared/`: shared schemas/constants used by bot and webapp.

## Bot Layering

The bot code follows a practical clean-architecture split:

```text
core -> infrastructure -> routers/interface
      -> db adapters
```

- `bot/core/`: entities, value objects, interfaces, use cases.
- `bot/infrastructure/`: service implementations, persistence adapters, workers.
- `bot/db/`: database models, session handling, low-level requests.
- `bot/routers/`: aiogram handlers and user-facing flows.
- `bot/services/` and `bot/other/`: integrations/utilities used by routers and infrastructure.

## DeName payment resolution

`DeNameService` in `bot/infrastructure/services/` reads the public-network
`dens-api` through `AppContext`. Set `DENAME_API_BASE_URL` to a trusted HTTPS
mainnet endpoint ending in `/api/v1`; the bot rejects the `/testnet/api/v1`
path. Leaving it unset disables name payments while keeping other recipient
formats available. The API hostname and its Stellar network must be checked
during deployment; the read API does not expose a network identity endpoint.

The Send router accepts `<name>.<tld>`, uses the indexed `records.forward`
account rather than `owner`, and requires an active, unexpired record. It also
checks the root-registry and matching TLD indexer stream: each must be idle
and updated within 120 seconds, and the TLD stream must have processed the
name's last event ledger. The HTTP client uses a four-second timeout per request and
at most one retry for network or server failure. A missing, malformed, inactive,
unresolved, or stale result stops the payment. It resolves the name again before
building the payment XDR and stops if the destination changed. The confirmation
shows both the full name and account ID. Indexing is eventually consistent;
this check is a freshness policy, not atomic on-chain resolution. Users must
review the displayed account ID before signing.

## Boundary Rules (Mechanically Checked)

Checked by `.linters/check_import_boundaries.py`:

1. `bot/core/entities`, `bot/core/value_objects`, `bot/core/interfaces` must not
   import from runtime outer layers:
   - `infrastructure`
   - `routers`
   - `middleware`
   - `keyboards`
   - `services`
   - `other`
2. `bot/core/entities` and `bot/core/value_objects` also must not import from
   `db`.
3. `bot/core/use_cases` must not import from delivery/presentation layers:
   - `routers`
   - `middleware`
   - `keyboards`

These are intentionally minimal and can be tightened as code is migrated.

## Test Layout

Primary tests live in `bot/tests/`, not in the root `tests/` directory.

- Router tests: `bot/tests/routers/`
- Core tests: `bot/tests/core/`
- Infrastructure tests: `bot/tests/infrastructure/`

See `bot/tests/README.md` for required fixtures and router test rules.

## Delayed Blockchain Notifications

Blockchain-originated wallet events use a delivery path separate from UI
screens. Redis stores the absolute sliding hold deadline, ordered per-user
pending queue, idempotency metadata, due-user schedule, and token-owned flush
locks. A polling worker processes expired deadlines in tracked per-user flush
tasks bounded by its batch size. One stuck flush therefore cannot block later
polls while the worker keeps task ownership and exception handling explicit.

`NotificationCoordinator` is the orchestration boundary for activity touches,
durable event acceptance, ordered flushes, and logical flow completion.
Redis decides only when a notification is released. `NotificationService` is
the sole Telegram sender for both immediate and queued delivery, using the
legacy `clear_last_message_id()` plus `cmd_info_message()` path. Consequently,
notifications use the settings/Return keyboard and replace the tracked
`last_message_id` like other legacy notification screens. The pending badge is
derived from a base inline keyboard stored outside FSM and is best-effort only.

See `adr/0001-delayed-blockchain-notification-delivery.md` for the base Redis
queue and at-least-once delivery trade-off. See
`adr/0002-worker-owned-notification-flow-completion.md` for hold-generation
keys, update-entry fencing, bounded worker tasks, and heartbeat ownership.

## Decision Record Policy

Any architecture-level change should be documented via a new ADR file under
`adr/` using `adr/template.md`.
