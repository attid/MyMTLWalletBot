# fix-offlimits-toggle: Fix OffLimits 5000 toggle not persisting

## Context

User report: the "Убрать все лимиты" (OffLimits) button in settings does not work.
Root cause (diagnosed 2026-10-03): `cb_set_limit` in `bot/routers/common_start.py`
toggles `can_5000` on the transient `User` entity returned by
`IUserRepository.get_by_id()` — the mutation never reaches the DB. The trailing
`await session.commit()` commits an empty session. Tests passed only because the
fixture returns a `MagicMock` user and the test asserts on the same mock
(tautology). Note: the code comment "IUserRepository does not have a general
update method" is stale — `update()` exists and persists `can_5000`.

## Files/Directories To Change

- `bot/routers/common_start.py` (handler `cb_set_limit`)
- `bot/tests/routers/test_common_start.py` (test `test_cb_set_limit_toggle`)
- `docs/exec-plans/active/2026-10-03-fix-offlimits-toggle.md` (this plan)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User (2026-10-03): "говорят в настрйоках кнопка отключить лимит 5000 не срабатывает. глянь, пока ничего не праввь"
> then: "ок давай исправим." — approving the diagnosed fix (router handler + test).

## Change Plan

1. [x] In `cb_set_limit`: toggle via `UpdateUserProfile` use case
   (`can_5000=1 if db_user.can_5000 == 0 else 0`), keep `session.commit()`.
   Remove the stale comment about a missing update method.
2. [x] Rewrite `test_cb_set_limit_toggle` so the mock repo has a persistent
   store: `update()` must apply through the use case and be observable on the
   next `get_by_id` (no tautology).
3. [x] Update docs only if contracts change (not expected).

## Risks / Open Questions

- `UpdateUserProfile.execute` re-reads the user by id; entity from the first
  `get_by_id` is only read for the current value — no double-write risk.
- Keyboard state after toggle is rendered from the return value of
  `execute()` / recomputed value, not from the detached entity.

## Verification

- `just test-fast` (or targeted pytest for tests/routers/test_common_start.py)
- `just check-fast` before commit.
- Result (2026-10-03): `just check-fast` passed — 477 tests, arch/lint checks green.