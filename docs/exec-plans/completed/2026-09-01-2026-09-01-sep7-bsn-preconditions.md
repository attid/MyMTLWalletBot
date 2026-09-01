# 2026-09-01-sep7-bsn-preconditions: Preserve SEP-7 challenge preconditions

## Context

BSN validates SEP-7 callback submissions against its cached challenge transaction,
allowing replacement only of the source account, sequence, and fee. MMBB currently
replaces the challenge time bounds with a new 180-second timeout while rebuilding it.

## Files/Directories To Change

- `bot/core/use_cases/stellar/process_uri.py`
- `bot/tests/core/test_process_uri_real.py`
- `docs/exec-plans/active/2026-09-01-2026-09-01-sep7-bsn-preconditions.md`
- `docs/exec-plans/completed/2026-09-01-2026-09-01-sep7-bsn-preconditions.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "Implement and verify the MMBB fix in /home/itolstov/Projects/mtl/mmwb_bot."

## Change Plan

1. [x] Preserve the cached challenge transaction body while replacing source,
   sequence, and fee in `process_uri.py`.
2. [x] Add a focused regression test proving min/max time bounds and all
   BSN-relevant immutable transaction fields survive rebuilding.
3. [x] Run the focused regression test and repository verification gate.
4. [x] Complete and archive this execution plan.

## Risks / Open Questions

- Stellar SDK builders expose precondition components individually, so the copy
  must include every component rather than only `time_bounds`.
- Existing untracked `.claude/` content must remain untouched.

## Verification

- `uv run pytest bot/tests/core/test_process_uri_real.py -q`
- `just check-fast`
- Expected: focused SEP-7 regression and the CI-safe gate pass.
