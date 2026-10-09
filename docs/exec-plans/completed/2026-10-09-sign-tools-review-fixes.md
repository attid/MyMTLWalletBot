# sign-tools-review-fixes: Fix review findings in sign_tools description flow

## Context

Follow-up to 2026-10-09-sign-tools-description (commit f7aa0bd). An external
review of the merged feature found 10 issues; all 10 were verified as real and
are fixed here. Same approved scope as the original task: human-readable
description for eurmtl.me sign_tools links in webapp memo + chat before/after
signing.

## Files/Directories To Change

- `bot/other/tx_render.py`
- `bot/other/stellar_tools.py`
- `bot/routers/sign.py`
- `bot/infrastructure/workers/signing_worker.py`
- `bot/tests/other/test_tx_render.py`
- `bot/tests/routers/test_sign_tools_description.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> Task originates from the owner-ordered review-fix cycle for the same files as
> commit f7aa0bd; the review findings were verified and fixes ordered by the
> owner ("Чиню." accepted, fixes are the direct continuation of the approved
> sign_tools description task).

## Change Plan

1. [x] `tx_render.py`: LiquidityPoolAsset no longer crashes (`_asset_str`
       fallback), per-op try/except so one exotic op can't kill the preview,
       HTML-escape of externally controlled strings (home_domain, data_name),
       `_short_key` actually shortens long keys, ManageData `b""` is a value
       not a deletion.
2. [x] `stellar_tools.py` `get_eurmtl_xdr`: strict hash extraction (query,
       fragment, trailing slash safe), hex-64 validation, dict/type checks on
       the API response, `import re`.
3. [x] `routers/sign.py` `cmd_check_xdr`: single HTTP call (description reuse),
       escape(operation), raw-XDR branch clears stale sign_tools FSM fields.
4. [x] `routers/sign.py` `cmd_ask_pin`: description takes priority over
       technical render lines in the sign header.
5. [x] `signing_worker.py`: post-signing message leads with the description.
6. [x] Tests updated to new expectations (short keys, description priority).
7. [x] Run `just check`.

## Risks / Open Questions

- None blocking: FSM contract unchanged, only sign_tools branch messages.

## Verification

- `just lint` — green (ruff + mypy).
- `just test-fast` — 533 passed.
- `just arch-test` — green.
- `bot/tests/` full run — 922 passed, 8 deselected.
