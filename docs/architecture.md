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

## Decision Record Policy

Any architecture-level change should be documented via a new ADR file under
`adr/` using `adr/template.md`.
