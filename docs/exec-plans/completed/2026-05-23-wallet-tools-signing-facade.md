# wallet-tools-signing-facade: Migrate wallet and tools signing

## Context

Next migration slice for moving user-facing XDR signing to
`SigningFacade`/`SignatureRequest`. Wallet settings and MTL tools currently
store loose XDR fields or call `PinState`/`cmd_ask_pin` directly. They should
store pending signature requests or call the facade while preserving
compatibility fields.

## Files/Directories To Change

- `bot/routers/wallet_setting.py`
- `bot/routers/mtlap.py`
- `bot/routers/mtltools.py`
- `bot/tests/routers/test_wallet_setting.py`
- `bot/tests/routers/test_mtlap.py`
- `bot/tests/routers/test_mtltools.py`
- `docs/exec-plans/active/2026-05-23-wallet-tools-signing-facade.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add failing tests for available wallet/tool pending `SignatureRequest`
   storage or facade requests.
2. [x] Migrate wallet-setting confirmation XDR storage and direct signing prompts.
3. [x] Migrate MTLAP confirmation XDR storage.
4. [x] Migrate MTL tools confirmation XDR storage.
5. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Keep legacy `xdr` fields during this larger migration.
- Some MTL tools may have thin coverage; add targeted tests where practical.

## Verification

- `uv run pytest bot/tests/routers/test_wallet_setting.py bot/tests/routers/test_mtlap.py bot/tests/routers/test_mtltools.py`
- `just check-fast`
- `git diff --check`
