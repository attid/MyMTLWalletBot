# sealedbox-project-patterns: Align sealed-box flow with project UI patterns

## Context

The sealed-box Telegram flow diverges from established callback and file-result
patterns. It starts a second UI message, deletes documents before download, and
returns result documents without a Home button.

## Files/Directories To Change

- `bot/routers/sealedbox.py`
- `bot/tests/routers/test_sealedbox.py`
- `docs/plans/2026-08-12-stellar-sealedbox-design.md`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++" after the exact path list and agreed behavior.

## Change Plan

1. [x] Add failing regressions for callback screen editing, download-before-delete,
   and result-document Home navigation.
2. [x] Align callback entry and sensitive message handling with existing project
   patterns.
3. [x] Send result documents with the shared Return keyboard and remove the
   previous tracked UI screen.
4. [x] Correct the design document and run full verification.

## Risks / Open Questions

- A result document is not managed by the shared text-screen sender, so its Home
  callback must remain accepted after tracked UI cleanup.
- A document must be fully downloaded before deletion while still guaranteeing
  deletion before cryptographic processing.

## Verification

- `uv run pytest bot/tests/routers/test_sealedbox.py`
- `just check-fast`
- `just test`
- All checks pass and regressions observe the expected Telegram API ordering.
