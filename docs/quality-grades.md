# Quality Grades

This document tracks quality baseline by area. Grades are directional and should
trend upward over time.

## Grade Scale

- `A`: stable, clear boundaries, strong tests, low drift
- `B`: mostly stable, minor debt
- `C`: notable debt, inconsistent patterns
- `D`: high risk, requires focused refactor

## Current Snapshot

| Area | Grade | Notes |
| --- | --- | --- |
| `bot/core` | B | Layer split exists; boundary checks are now codified but still minimal. |
| `bot/routers` | B | Good feature coverage; legacy patterns still mixed in some handlers. |
| `bot/infrastructure` | C | Broad responsibilities and historical coupling need incremental cleanup. |
| `bot/db` | B | Core persistence works, but commit discipline must stay explicit everywhere. |
| `webapp` | B | Small and focused; needs stronger CI/test depth over time. |
| `shared` | A | Small, clear scope, low complexity. |
| Docs/Guardrails | C | New baseline added; next step is stricter checks and continuous upkeep. |

## Upgrade Priorities

1. Increase architecture checks in `.linters/` gradually.
2. Expand deterministic tests around risky router/infrastructure flows.
3. Keep docs synchronized with behavior and contracts.
