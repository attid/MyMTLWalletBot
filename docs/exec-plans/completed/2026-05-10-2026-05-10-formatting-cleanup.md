# 2026-05-10-formatting-cleanup: Format touched Python files

## Context

After the functional wallet/MTL tools commit, a small set of Python files still
had formatting-only changes. Keep those changes isolated in a separate commit.

## Files/Directories To Change

- `bot/keyboards/webapp.py`
- `bot/other/soroban_render.py`
- `bot/tests/infrastructure/test_telegram_utils.py`
- `bot/tests/other/test_soroban_render.py`
- `bot/tests/other/test_stellar_tools.py`
- `docs/exec-plans/active/2026-05-10-2026-05-10-formatting-cleanup.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> да ок давай. можем закомить первое, потом пргнать везде форматинг, если будут изменения то тесты и линк и тогда уже отдельный комит с форматингом

## Change Plan

1. [x] Commit the functional changes separately first.
2. [x] Run repository formatting.
3. [x] Keep only formatting-only Python changes in this commit.
4. [x] Run lint and tests.
5. [x] Move this plan to completed before committing.

## Risks / Open Questions

- No behavior changes intended.

## Verification

- `just fmt`
- `just lint`
- `just test`
