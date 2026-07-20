# stellar-operation-error: Show failing Stellar operation number

## Context

Horizon returns one operation result code per attempted operation. Successful
operations can precede the actual failure, but the current formatter always
renders the first code and can therefore report `op_success` as the error.

## Files/Directories To Change

- `bot/other/stellar_error_codes.py`
- `bot/tests/other/test_stellar_error_codes.py`
- `docs/exec-plans/active/2026-07-20-stellar-operation-error.md`
- `docs/exec-plans/completed/2026-07-20-stellar-operation-error.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User replied `++` after the proposed production and regression-test paths;
> execution-plan Markdown is allowed by the repository intake protocol.

## Change Plan

1. [x] Add a regression test for `op_success`, `op_success`, `op_low_reserve`.
2. [x] Make the formatter select the first non-success operation while preserving
       its one-based operation number.
3. [x] Render the raw code together with its human-readable description.
4. [x] Run focused tests and `just check-fast`.
5. [x] Move this completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- Horizon may omit operations after the first failure; deriving the operation
  number from the result-code index remains correct for the attempted prefix.
- Preserve transaction-level fallback behavior when no operation failure exists.

## Verification

- `uv run pytest bot/tests/other/test_stellar_error_codes.py -q`
- `uv run pytest bot/tests/test_signing_flow.py::TestSubmitSignedXdr -q`
- `just check-fast`
- Expected: all commands pass; failure output includes operation number, raw code,
  and human-readable description.
