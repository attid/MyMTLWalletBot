# balance-cache-ttl: Add TTL fallback for wallet balance cache

## Context

Balance cache can remain stale when event-based invalidation does not fire or
does not advance `last_event_id`. Add a TTL fallback so cached balances are
used only when they are both event-valid and fresh enough.

## Files/Directories To Change

- `bot/core/use_cases/wallet/get_balance.py`
- `bot/core/domain/entities.py`
- `bot/core/interfaces/repositories.py`
- `bot/infrastructure/persistence/sqlalchemy_wallet_repository.py`
- `bot/db/models.py`
- `bot/tests/core/test_get_balance.py`
- `bot/tests/infrastructure/test_infrastructure_repositories.py`
- `docs/exec-plans/active/2026-03-26-balance-cache-ttl.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> +

## Change Plan

1. [x] Add failing tests for stale balance cache and timestamp reset behavior.
2. [x] Extend wallet model/entity/repository mapping with `balances_updated_at`.
3. [x] Apply TTL fallback in `GetWalletBalance` so cache older than 1 hour refreshes from Stellar.
4. [x] Keep reset behavior clearing both cached balances and their timestamp.
5. [x] Run targeted tests for use case and repository behavior.

## Risks / Open Questions

- Introducing a new DB field must not break existing wallets with null timestamp values.
- TTL should be a fallback only and must not override existing event-based invalidation logic.

## Verification

- `uv run pytest bot/tests/core/test_get_balance.py -q`
- `uv run pytest bot/tests/infrastructure/test_infrastructure_repositories.py -q`
- `just lint`
- Expected signals: stale-cache regression test fails before the fix, then both targeted suites pass after implementation.
