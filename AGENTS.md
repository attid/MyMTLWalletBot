# Repository Guidelines

## Project Structure & Module Organization
`start.py` wires the Aiogram dispatcher, middleware, routers, APScheduler jobs, and background workers (`cheque_worker`, `usdt_worker`, etc.), so new components must be registered there. Functional flows reside in `routers/` (wallet ops, swaps, TON, admin), while shared logic sits in `middleware/`, `services/`, and `db/` (SQLAlchemy pool, models, requests). Cross-cutting helpers such as Stellar/TRON clients, localization, config readers, and global state live in `other/`. Localized strings are JSON files in `langs/`, assets/logs stay in `data/` and `logs/`, and deployment helpers live in `deploy/`.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: expected Python 3.12 virtual environment.  
- `pip install -r requirements.txt`: install Aiogram, SQLAlchemy, Tron/Stellar SDKs, FastStream, etc.  
- `bash start.sh`: idempotent entry point that prepares the venv and launches the bot.  
- `python start.py`: quick reload when the environment is already active.  
- `bash clean.sh`: strip `__pycache__` and `*.log` clutter before committing or packaging.  
Run commands from the repo root so relative imports and path-based config resolve cleanly.

## Coding Style & Naming Conventions
Adhere to PEP8 (4 spaces, ≤100 chars) and keep business logic async-friendly—avoid blocking calls inside handlers. Modules, functions, and JSON keys use `snake_case`; classes remain `PascalCase`; router instances are exported as `router`. Log via `loguru.logger`, reuse existing middleware for DB/throttling, and place human-facing copy inside `langs/*.json` (HTML markup only).

## Testing Guidelines
A formal `tests/` suite is still emerging; add new coverage with `pytest`/`pytest-asyncio`, mocking external ledgers and Redis. Prefer scenario tests that drive routers via `dp.feed_update()` plus unit tests for helpers in `other/`. **Any router tests without `mock_server` are considered invalid.** Exercise scheduler jobs and middleware in isolation, and log manual Telegram checks in the PR when automated coverage is not feasible.

## Commit & Pull Request Guidelines
Follow the current convention: emoji + tag + scope (`🐛 fix(routers/send.py): memo fallback`) with subjects ≤72 chars and descriptive bodies. Each PR should state the problem, highlight risky areas, list test evidence, and link the relevant ticket. Attach screenshots or transcript snippets for UI-visible changes and note any config, migration, or deploy steps.

## Security & Configuration Tips
Secrets load via `other/config_reader.py`; `.env` stays untracked, and different tokens are exposed through `config.test_mode`. Validate user input before calling blockchain clients, rely on throttling/logging middleware, and keep private keys encrypted at rest. Update `deploy/mmwb_bot.*.sh` when service names or systemd units change, and scrub logs via `clean.sh` before sharing traces.

## Task Intake Protocol
- For each new task, first analyze the requirements and explicitly state which files or directories need to change.
- Do not edit any files until there is direct permission that names the specific file(s) or directory that may be modified—no exceptions.
