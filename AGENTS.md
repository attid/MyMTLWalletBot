# Repository Guidelines

## Project Structure & Module Organization
`start.py` wires the Aiogram dispatcher, middleware, routers, APScheduler jobs, Redis/FastStream broker, and background workers (`cheque_worker`, `usdt_worker`, `events_worker`, etc.), so new components must be registered there. Functional flows live in `routers/` (wallet ops, swap, send, TON, admin, URI), while shared HTTP/ledger logic sits in `other/` and `services/`. Database access is in `db/` (pool, models, requests) and `infrastructure/persistence/` (SQLAlchemy repositories). Domain/clean-architecture layers are in `core/` (entities, value objects, interfaces, use cases) and `infrastructure/` (services, factories, scheduler, monitoring, workers, utils). Cross-cutting middleware stays in `middleware/`, keyboards in `keyboards/`, and localization JSON in `langs/`. Assets/logs stay in `data/` and `logs/`, deployment scripts live in `deploy/`, and architecture notes live in `docs/clean_architecture/`.

## Build, Test, and Development Commands
- `python3.12 -m venv .venv && source .venv/bin/activate`: expected Python 3.12 virtual environment.  
- `pip install -r requirements.txt`: install Aiogram, SQLAlchemy, FastStream, Stellar/TRON SDKs, etc.  
- `bash start.sh`: idempotent entry point that prepares the venv and launches the bot.  
- `python start.py`: quick reload when the environment is already active.  
- `uv run pytest tests/`: preferred test runner (see `tests/README.md`).  
- `bash clean.sh`: strip `__pycache__` and `*.log` clutter before committing or packaging.  
Run commands from the repo root so relative imports and path-based config resolve cleanly.

## Coding Style & Naming Conventions
Adhere to PEP8 (4 spaces, ≤100 chars) and keep business logic async-friendly—avoid blocking calls inside handlers. Modules, functions, and JSON keys use `snake_case`; classes remain `PascalCase`; router instances are exported as `router`. Log via `loguru.logger`, reuse existing middleware for DB/throttling, and place human-facing copy inside `langs/*.json` (HTML markup only).

## Database Transaction Management
**CRITICAL:** `db_pool.get_session()` does **NOT** auto-commit on context exit (`db/db_pool.py:83` is commented out). All database modifications **MUST** have explicit `await session.commit()` after UPDATE/INSERT/DELETE operations.

**Rules:**
1. **Always add `await session.commit()`** after repository methods that modify data (update_*, create_*, delete_*, set_*)
2. **Place commit in the same `async with session` block** as the modification
3. **Repository methods use `flush()` not `commit()`** - commit is caller's responsibility
4. **Use cases return without commit** - handlers/routers must commit
5. **Test data persistence** - verify changes survive session closure (see `tests/infrastructure/test_usdt_balance_commit.py` example)

**Example:**
```python
# ❌ WRONG - changes NOT saved
async with db_pool.get_session() as session:
    repo = factory.get_user_repository(session)
    await repo.update_lang(user_id, "en")
    # Missing commit!

# ✅ CORRECT - changes saved
async with db_pool.get_session() as session:
    repo = factory.get_user_repository(session)
    await repo.update_lang(user_id, "en")
    await session.commit()  # Required!
```

## Testing Guidelines
A formal `tests/` suite is still emerging; add new coverage with `pytest`/`pytest-asyncio`, mocking external ledgers and Redis. **You MUST read `tests/README.md` before modifying or creating tests to ensure compliance with naming rules.** Prefer scenario tests that drive routers via `dp.feed_update()` plus unit tests for helpers in `other/`. **Any router tests without `mock_server` are considered invalid.** Exercise scheduler jobs and middleware in isolation, and log manual Telegram checks in the PR when automated coverage is not feasible.

## Commit & Pull Request Guidelines
Follow the current convention: emoji + tag + scope (`🐛 fix(routers/send.py): memo fallback`) with subjects ≤72 chars and descriptive bodies. Each PR should state the problem, highlight risky areas, list test evidence, and link the relevant ticket. Attach screenshots or transcript snippets for UI-visible changes and note any config, migration, or deploy steps.

## Security & Configuration Tips
Secrets load via `other/config_reader.py`; `.env` stays untracked, and different tokens are exposed through `config.test_mode`. Validate user input before calling blockchain clients, rely on throttling/logging middleware, and keep private keys encrypted at rest. Update `deploy/mmwb_bot.*.sh` when service names or systemd units change, and scrub logs via `clean.sh` before sharing traces.

## Task Intake Protocol
- For each new task, first analyze the requirements and explicitly state which files or directories need to change.
- Do not edit any files until there is direct permission that names the specific file(s) or directory that may be modified—no exceptions.
