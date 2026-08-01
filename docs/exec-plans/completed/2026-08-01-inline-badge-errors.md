# inline-badge-errors: Fix inline search and stale badge errors

## Context

Production log `localdoc/log1.log` contains repeated Firebird truncation errors
when a Stellar URI is sent through Telegram inline mode and a full traceback
when a notification badge targets a deleted Telegram message. Together these
known conditions occupy roughly 84% of the log excerpt.

## Files/Directories To Change

- `bot/routers/send.py`
- `bot/infrastructure/persistence/sqlalchemy_user_repository.py`
- `bot/infrastructure/services/notification_badge_service.py`
- `bot/tests/routers/test_send.py`
- `bot/tests/infrastructure/test_infrastructure_repositories.py`
- `bot/tests/infrastructure/test_notification_badge_service.py`
- `docs/exec-plans/active/2026-08-01-inline-badge-errors.md`
- `docs/exec-plans/completed/2026-08-01-inline-badge-errors.md`
- `docs/plans/2026-08-01-inline-badge-errors.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> The assistant listed the three production files, three test files, and
> Markdown execution plan paths. After the design explanation, the user
> replied `++`.

## Change Plan

1. [x] Add RED router and repository tests for non-username/oversized inline
       input.
2. [x] Restrict username lookup to username-shaped inline text and protect the
       Firebird repository boundary from oversized patterns.
3. [x] Add a RED badge test for `message to edit not found`.
4. [x] Clear the stale base-markup record and emit one compact non-error log
       for that known Telegram response.
5. [x] Verify focused suites, `just check-fast`, and `just test`.
6. [x] Move the completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- Partial username searches must continue to work for valid Telegram username
  characters.
- Unknown database and Telegram errors must remain visible with full traceback.
- Stale badge cleanup must occur while the existing per-user UI lease is held.

## Verification

- `uv run pytest bot/tests/routers/test_send.py -q`
- `uv run pytest bot/tests/infrastructure/test_infrastructure_repositories.py -q`
- `uv run pytest bot/tests/infrastructure/test_notification_badge_service.py -q`
- `just check-fast`
- `just test`
- Expected: Stellar URI never reaches username search; oversized repository
  input never reaches Firebird; missing badge message clears its Redis record
  without an ERROR event; unknown failures remain errors.

Results:

- RED: all three new focused tests failed against the original implementation.
- Focused suites: `57 passed`.
- `just check-fast`: Ruff and mypy passed; `589 passed`; architecture and docs
  checks passed.
- `just test`: `900 passed, 7 deselected`.
