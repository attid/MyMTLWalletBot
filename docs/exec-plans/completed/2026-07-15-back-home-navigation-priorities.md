# back-home-navigation-priorities: Align Back/Home rollout with product priorities

## Context

The initial repository-wide Back/Home master plan included legacy TON flows and
low-use cheque flows too early. Align the documentation with the user-approved
product priority: Trade, Assets, MTL Tools/MTLAP, wallet onboarding/signing,
then audit and full regression.

## Files/Directories To Change

- `docs/exec-plans/active/2026-07-15-back-home-navigation-priorities.md`
- `docs/plans/2026-07-15-back-home-navigation-rollout-design.md`
- `docs/plans/2026-07-15-back-home-navigation-rollout.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "TON у нас легаласи, его не трогаем. чеки тоже не используються практически, отложим их. ордера и трейд важнее всего. потом ассетс. потом MTL Tools и MTLAP. потом Добавление кошелька, PIN/password и signing. аудит и регрес тесты да."

## Change Plan

1. [x] Remove TON and Cheques from the active implementation sequence and
   record them as legacy/deferred exclusions.
2. [x] Reorder functional slices to Trade, Assets, MTL Tools/MTLAP, then wallet
   onboarding/signing.
3. [x] Consolidate remaining used-function discovery into the audit slice.
4. [x] Preserve the final repository-wide regression task.
5. [x] Validate documentation and execution-plan guardrails.

## Risks / Open Questions

- Deferred flows must remain explicitly listed so a future audit does not
  accidentally pull them back into scope.
- Reordering must preserve signing/data-safety dependencies between slices.

## Verification

- `uv run python .linters/check_docs_contract.py`
- `uv run python .linters/check_exec_plan_scope_lock.py`
- `git diff --check`
- Expected: all checks pass and no runtime file is modified.
