# precommit-completed-plan-fix: Fix pre-commit completed-plan handling

## Context

Why this task exists and links to issue/ADR.

## Files/Directories To Change

- `.githooks/pre-commit`
- `docs/exec-plans/active/2026-03-31-precommit-completed-plan-fix.md`
- `docs/exec-plans/completed/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [ ] Reproduce the failing `pre-commit` behavior on a staged set that contains only a completed execution plan.
2. [ ] Update `.githooks/pre-commit` so the completed-plan check handles the "no active plans staged" case without failing under `set -euo pipefail`.
3. [ ] Re-run `.githooks/pre-commit` and verify it exits successfully for the current staged set.
4. [ ] Move this execution plan to `docs/exec-plans/completed/` after all items are done.
5. [ ] Retry normal `git commit` and `git push` without `--no-verify`.

## Risks / Open Questions

- The hook fix must not weaken the existing guardrail that requires some execution plan file to be staged.
- The current staged set for the notifier fix must remain intact while fixing the hook.

## Verification

- `bash -x .githooks/pre-commit`
- The hook currently exits non-zero before the fix and exits zero after the fix for the current staged set.
