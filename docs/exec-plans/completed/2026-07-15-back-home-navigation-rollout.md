# back-home-navigation-rollout: Plan repository-wide Back/Home navigation rollout

## Context

Send and Swap already distinguish flow-local Back (`FlowBack`) from global
Home (`Return`). Inventory the remaining bot functions and create a master
rollout plan that applies the same established contract without changing code.

## Files/Directories To Change

- `docs/exec-plans/active/2026-07-15-back-home-navigation-rollout.md`
- `docs/plans/2026-07-15-back-home-navigation-rollout-design.md`
- `docs/plans/2026-07-15-back-home-navigation-rollout.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "давай дальнейшее разделение кнопок назад\\домой сделаем чтоб все функции этим обладали, сделай большой план"

Markdown planning files may be edited under the repository Task Intake
Protocol without separately naming every documentation path.

## Change Plan

1. [x] Record the already established Send/Swap Back/Home contract as the
   rollout baseline.
2. [x] Inventory remaining FSM and menu flows, their navigation keyboards,
   terminal screens, signing boundaries, and router tests.
3. [x] Group implementation into independently executable functional slices
   with exact production/test paths and ordering constraints.
4. [x] Write the master design and implementation plan under `docs/plans/`.
5. [x] Validate documentation and scope guardrails without changing runtime
   code.

## Risks / Open Questions

- Back mappings must be derived from each existing state transition rather
  than inferred from labels alone.
- Signing and successful terminal screens must not permit navigation back to
  a transaction that has already been submitted.
- Global Home must continue to clear FSM state, complete notification flow,
  and release pending notifications.
- Notification-message keyboards remain outside the flow-local Back rollout.

## Verification

- `uv run python .linters/check_docs_contract.py`
- `uv run python .linters/check_exec_plan_scope_lock.py`
- `git diff --check`
- Expected: all documentation and execution-plan checks pass; no runtime files
  are modified.
