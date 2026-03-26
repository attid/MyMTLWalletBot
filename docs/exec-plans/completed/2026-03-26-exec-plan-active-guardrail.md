# exec-plan-active-guardrail: Block commits for fully completed active execution plans

## Context

The current pre-commit hook only checks that some execution plan file is
staged when committing code under `bot/`, `webapp/`, or `shared/`. It does not
prevent a fully completed plan from remaining in `docs/exec-plans/active/`,
which allowed inconsistent final commits.

## Files/Directories To Change

- `AGENTS.md`
- `.githooks/pre-commit`
- `docs/exec-plans/active/2026-03-26-exec-plan-active-guardrail.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> +

## Change Plan

1. [x] Reproduce the missing guardrail with a staged fully-completed active plan.
2. [x] Add explicit process rule in `AGENTS.md` that completed plans must move to `completed/` before final commit.
3. [x] Extend `.githooks/pre-commit` to block staged fully-completed plans that remain in `active/`.
4. [x] Re-run the hook reproduction to verify intermediate active plans still pass and fully completed ones fail.
5. [x] Run targeted verification for the updated hook logic.

## Risks / Open Questions

- The hook must not block legitimate in-progress commits with unfinished plans in `active/`.
- Local clones without `core.hooksPath=.githooks` will not enforce the new guardrail until configured.

## Verification

- Manual hook verification in a temporary git repo using staged active plan files.
- `bash -n .githooks/pre-commit`
- Expected signals: unfinished active plan is allowed; fully completed active plan is rejected with a clear message.
