# fix-mtltools-test-wallet-fixture: Align MTLTools wallet fixture with repository contract

## Context

The MTLTools missing-account regression configures SQLAlchemy's old
`scalar_one_or_none()` result shape. `get_default_wallet()` now consumes
`scalars().all()`, so the test sends a `MagicMock` account to Horizon instead
of the intended unfunded public key and fails to exercise the production 404
handling.

## Files/Directories To Change

- `bot/tests/routers/test_mtltools.py`
- `docs/exec-plans/active/2026-07-18-fix-mtltools-test-wallet-fixture.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++"

## Change Plan

1. [x] Preserve the existing RED evidence for Delegate and Donate missing-account
   cases.
2. [x] Update the local session fixture to return the configured wallet through
   `scalars().all()`.
3. [x] Run the focused MTLTools suite and full repository test suite.
4. [x] Run repository gates and move this plan to completed.

## Risks / Open Questions

- The change must repair only the test boundary and must not mock or bypass the
  real `stellar_get_data()`/mock Horizon path.

## Verification

- `uv run pytest bot/tests/routers/test_mtltools.py -q`
- `just test`
- `just check-fast`
- `git diff --check`
- Expected: Horizon receives `UNFUNDED_STELLAR_ACCOUNT`, returns 404, both
  handlers show `send_error2`, and the full suite passes.

Verification evidence:

- RED: both parametrized missing-account cases failed by rendering the normal
  Delegate/Donate menus instead of `send_error2`.
- Focused MTLTools suite: `9 passed`.
- Full `just test`: `854 passed`, `7 deselected`, no failures.
- `just check-fast`: Ruff, Mypy, architecture/docs checks passed; `546 passed`.
- `git diff --check`: passed; production code unchanged.
