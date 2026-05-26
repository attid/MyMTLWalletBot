# start-normalize-default-wallets: Normalize duplicate default wallets on start

## Context

Production DB can contain multiple active default wallets for one user. The
previous fix makes reads tolerant, but the user cannot manually clean the DB.
Add self-healing on the start/balance path: normalize duplicate active defaults
to one wallet before rendering the main screen.

## Files/Directories To Change

- `bot/core/interfaces/repositories.py`
- `bot/infrastructure/persistence/sqlalchemy_wallet_repository.py`
- `bot/routers/start_msg.py`
- `bot/tests/infrastructure/test_infrastructure_repositories.py`
- `bot/tests/routers/test_start_msg.py`
- `docs/exec-plans/active/2026-05-26-start-normalize-default-wallets.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> requested self-healing on /start; markdown lifecycle paths allowed by AGENTS.md

## Change Plan

1. [x] Add RED repository test for normalizing multiple active defaults.
2. [x] Add RED start/balance test proving normalization is invoked before
   rendering.
3. [x] Add repository interface and SQLAlchemy implementation.
4. [x] Call normalization from start/balance flow.
5. [x] Run focused tests, `git diff --check`, and `just check-fast`.

## Risks / Open Questions

- Normalization must pick the same wallet as tolerant `get_default_wallet()`: the
  latest active default by id.
- Do not normalize deleted wallets.

## Verification

- `uv run pytest bot/tests/infrastructure/test_infrastructure_repositories.py bot/tests/routers/test_start_msg.py`
- `git diff --check`
- `just check-fast`
