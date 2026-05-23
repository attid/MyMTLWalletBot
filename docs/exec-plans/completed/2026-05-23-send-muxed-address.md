# send-muxed-address: Fix send token selection for muxed addresses

## Context

Sending to a Stellar muxed account (`M...`) reaches token selection with an
empty token list because recipient trustlines are looked up using the muxed
address. Horizon balance lookups need the underlying `G...` account, while the
payment destination should remain the original muxed address.

## Files/Directories To Change

- `bot/routers/send.py`
- `bot/tests/routers/test_send.py`
- `docs/exec-plans/completed/2026-05-23-send-muxed-address.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add a router regression test for entering an `M...` muxed address.
2. [x] Verify the regression test fails against current code.
3. [x] Store the original destination and the underlying balance lookup account
   separately in send state.
4. [x] Use the underlying account only for recipient balance/trustline lookup.
5. [x] Run focused send tests and `just check-fast`.

## Risks / Open Questions

- Keep payment destination as the original muxed address.
- Do not broaden the send flow beyond muxed address normalization.

## Verification

- `uv run pytest bot/tests/routers/test_send.py -k muxed`
  - Red before fix: `UNLIMITED` was missing from reply markup.
  - Green after fix: 1 passed, 12 deselected.
- `uv run pytest bot/tests/routers/test_send.py`
  - 13 passed.
- `just check-fast`
  - ruff, mypy core, 416 tests, import boundaries, docs contract, and exec plan scope-lock passed.
