# sealedbox-settings-menu: Move sealed-box entry to wallet settings

## Context

The sealed-box file encryption entry currently lives in MTL Tools. Move the
single entry button to wallet settings while preserving the existing
encrypt/decrypt submenu and flow behavior.

## Files/Directories To Change

- `bot/routers/wallet_setting.py`
- `bot/routers/mtltools.py`
- `bot/routers/sealedbox.py`
- `bot/tests/routers/test_wallet_setting.py`
- `bot/tests/routers/test_mtltools.py`
- `bot/tests/routers/test_sealedbox.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User confirmed one settings button and approved the listed paths with `++`.

## Change Plan

1. [x] Update router tests to require the sealed-box entry in wallet settings
   and exclude it from MTL Tools.
2. [x] Update the sealed-box navigation test so Back returns to wallet settings.
3. [x] Move the entry button and redirect the submenu Back callback with the
   smallest router-only implementation change.
4. [x] Run focused router tests and `just check-fast`.
5. [x] Finish the execution plan after all checks pass.

## Risks / Open Questions

- The wallet settings menu varies for free and non-free wallets; the entry must
  be available in both variants.
- Existing encryption, decryption, file deletion, and Home behavior must remain
  unchanged.

## Verification

- `uv run pytest bot/tests/routers/test_wallet_setting.py bot/tests/routers/test_mtltools.py bot/tests/routers/test_sealedbox.py -q`
- `just check-fast`
- Expected: all tests and architecture checks pass; the settings keyboard has
  one `SealedBoxMenu` entry, MTL Tools has none, and submenu Back renders
  `WalletSetting`.
