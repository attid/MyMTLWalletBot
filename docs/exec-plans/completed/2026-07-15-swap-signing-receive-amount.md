# swap-signing-receive-amount: Show destination amount in swap signing summary

## Context

The swap confirmation contains both source and destination amounts, but the
`operation` summary passed to the WebApp signing screen omits the destination
amount. A `/swap 500 USDC USDM` request is therefore shown as
`Swap 500 USDC → USDM` instead of including the calculated USDM amount.

## Files/Directories To Change

- `bot/routers/swap.py`
- `bot/tests/routers/test_swap.py`
- `webapp/templates/decode.html`
- `webapp/static/js/i18n.js`
- `bot/tests/other/test_webapp_decode_template.py`
- `docs/exec-plans/active/2026-07-15-swap-signing-receive-amount.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++"

## Change Plan

1. [x] Add failing regressions requiring destination amount and asset in the
   stored signing operation for command, strict-send, and strict-receive swaps.
2. [x] Add a failing WebApp Decode regression requiring strict-send,
   strict-receive, and full payment-path fields.
3. [x] Centralize the four-part swap operation summary and use it in all three
   construction paths.
4. [x] Render source/destination amounts and the complete asset path in WebApp
   Decode with Russian and English labels.
5. [x] Run focused Swap/Decode tests and repository gates.
6. [x] Move this plan to completed after verification.

## Risks / Open Questions

- Amount formatting must stay consistent with the existing confirmation text.
- The fix must not change XDR construction, path propagation, slippage, or
  signing behavior.
- Stellar SDK represents only intermediate assets in `operation.path`; the UI
  must prepend `sendAsset` and append `destAsset` to show the complete route.

## Verification

- RED/GREEN: focused operation assertions in
  `bot/tests/routers/test_swap.py`.
- `uv run pytest bot/tests/routers/test_swap.py -q`
- `uv run pytest bot/tests/other/test_webapp_decode_template.py -q`
- `just check-fast`
- `git diff --check`
- Expected: operation text is `Swap <send amount> <send asset> → <receive
  amount> <receive asset>` in every Swap signing request; all checks pass.

Verification evidence:

- RED: Swap suite reported 3 expected failures with the old three-part
  operation summary; Decode suite reported 2 expected failures for missing
  path-payment fields and labels.
- GREEN: focused Swap/Decode suite: `23 passed`.
- `just check-fast`: Ruff and Mypy passed; fast suite: `551 passed`; architecture,
  docs-contract, and scope-lock checks passed.
- `just test-e2e-smoke`: `117 passed`.
- Focused Ruff format check and `git diff --check`: passed.
- Full `just test`: `860 passed`, with 3 pre-existing out-of-scope failures in
  Fest and MTLTools; the user explicitly approved committing without resolving
  them.
