# cheque-trade-bsn-signing-facade: Migrate cheque trade bsn signing

## Context

Next migration slice for moving user-facing XDR signing to
`SigningFacade`/`SignatureRequest`. Cheque, trade, and BSN currently store loose
XDR or call `PinState`/`cmd_ask_pin` directly. They should store pending
signature requests or call the facade while preserving compatibility fields.

## Files/Directories To Change

- `bot/routers/cheque.py`
- `bot/routers/trade.py`
- `bot/routers/bsn.py`
- `bot/tests/routers/test_cheque.py`
- `bot/tests/routers/test_trade.py`
- `bot/tests/routers/test_bsn.py`
- `docs/exec-plans/active/2026-05-23-cheque-trade-bsn-signing-facade.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add failing tests for cheque/trade pending `SignatureRequest` storage.
2. [x] Add failing BSN test for facade request instead of direct `cmd_ask_pin`.
3. [x] Migrate cheque confirmation XDR storage to pending requests.
4. [x] Migrate trade confirmation XDR storage to pending requests.
5. [x] Migrate BSN direct signing prompt to `SigningFacade.request_signature`.
6. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Keep legacy `xdr` fields for compatibility during this larger migration.
- Preserve existing confirmation keyboards and post-submit callbacks.

## Verification

- `uv run pytest bot/tests/routers/test_cheque.py bot/tests/routers/test_trade.py bot/tests/routers/test_bsn.py`
- `just check-fast`
- `git diff --check`
