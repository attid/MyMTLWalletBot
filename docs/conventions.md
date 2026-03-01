# Conventions

## Code Style

- Python 3.12+
- PEP8-compatible formatting via Ruff
- Type checks via Mypy
- Keep modules focused and easy to scan

## Naming

- Modules/functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Router instance export name: `router`

## Async and Side Effects

- Keep handlers/use-cases async-safe; avoid blocking I/O in request handlers.
- Isolate external side effects in infrastructure/service boundaries.

## Database Transaction Rule

`db_pool.get_session()` does not auto-commit. For every write operation,
call `await session.commit()` in the same `async with` block.

## Test Conventions

- Read `bot/tests/README.md` before writing tests.
- Router tests must use `mock_telegram`.
- Prefer dependency injection over deep patching.
- Mock only external boundaries when possible.

## AI-First Delivery Conventions

- Keep diffs minimal and mechanical.
- Add/adjust docs whenever behavior or contracts change.
- For non-trivial tasks, create an execution plan in `docs/exec-plans/active/`.

## Static Analysis Scope

- `just lint` is the required gate for day-to-day work (`ruff` + `mypy core`).
- `just typecheck-full` is a debt visibility sweep over full `bot/`.
- `just check-fast` is the CI-safe validation gate.
