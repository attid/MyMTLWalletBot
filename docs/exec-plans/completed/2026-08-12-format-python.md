# format-python: Apply repository Python formatting

## Context

`just check` reports Python files that do not match the repository Ruff format.
The user requested running the full gate and committing those mechanical changes.

## Files/Directories To Change

- `bot/`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "запусти just check и закомить форматирование"

## Change Plan

1. [x] Run `just check` to apply Ruff formatting and execute the full gate.
2. [x] Verify the diff contains formatting-only changes under `bot/`.
3. [x] Scan the staged diff for secrets and commit the formatting.

## Risks / Open Questions

- Formatter output could include unexpected semantic changes; inspect every diff.

## Verification

- `just check`
- `git diff --check`
- Staged gitleaks scan reports no leaks.
