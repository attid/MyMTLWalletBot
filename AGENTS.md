# Agent Index

This repository follows an AI-first workflow. Keep this file short and use it as
an index. Detailed rules live in `docs/`.

## Where to Read First
- `AI_FIRST.md`: high-level contract and agent behavior.
- `docs/architecture.md`: real module boundaries for this monorepo.
- `docs/conventions.md`: coding and naming conventions.
- `docs/golden-principles.md`: non-negotiable engineering principles.
- `docs/quality-grades.md`: current quality baseline and debt map.
- `docs/glossary.md`: project language and key domain terms.
- `docs/runbooks/`: triage and operational checklists.
- `docs/exec-plans/`: active/completed execution plans.
- `adr/`: architecture decision records.

## Monorepo Layout
- `bot/`: Telegram bot code (`core/`, `infrastructure/`, `routers/`, `tests/`).
- `webapp/`: FastAPI-based signing app.
- `shared/`: shared schemas/constants.
- `.linters/`: local structural checks used by CI.

## Standard Commands
- `just fmt`: format code.
- `just lint`: static checks.
- `just test`: full test suite.
- `just test-fast`: fast local subset.
- `just test-e2e-smoke`: deterministic user-flow smoke tests.
- `just test-external`: docker/external integration tests.
- `just arch-test`: architecture guardrails.
- `just secret-scan`: repository secret leak scan (gitleaks).
- `just check`: full local gate (`fmt + lint + test + arch-test`).
- `just check-fast`: CI-safe gate (`lint + test-fast + arch-test`).
- `just metrics`: local repository metrics snapshot.
- `just start-task <id> title="..."`: create an execution plan stub.
- `just finish-task <plan-file>`: move plan from active to completed.
- `just typecheck-full`: full mypy sweep (legacy debt visibility).

## Non-Negotiable Rules
1. Do not guess data contracts or architecture; read docs first.
2. Keep diffs minimal and verifiable.
3. For DB writes in bot code, always call `await session.commit()` in the same
   `async with` session block.
4. Read `bot/tests/README.md` before adding/changing tests.
5. Router tests must use `mock_telegram`.
6. Do not weaken tests, linters, or CI checks to make a change pass.

## Task Intake Protocol
1. First state which files/directories need changes.
2. Do not edit until explicit permission names allowed paths.

## Post-Push Step
- After every successful `git push`, run `just push-gitdocker`.
