# wallet-expert-key-import: Restore expert wallet key import

## Context

The wallet import flow advertises expert mode as `private key + space + public key`.
Legacy implementation passed the second argument as the wallet address, but the
current bot router ignores it and always stores the public key derived from the
private key.

## Files/Directories To Change

- `bot/routers/add_wallet.py`
- `bot/tests/routers/test_add_wallet.py`
- `docs/exec-plans/active/2026-05-12-wallet-expert-key-import.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add a router test proving `secret public_key` stores `public_key`.
2. [x] Restore expert-mode parsing in `bot/routers/add_wallet.py`.
3. [x] Keep normal one-argument key import behavior unchanged.
4. [x] Run focused tests and a fast gate.

## Risks / Open Questions

- Expert mode stores a signer secret for a different wallet address; Stellar will
  only accept signed transactions if that secret is an authorized signer.

## Verification

- `uv run pytest bot/tests/routers/test_add_wallet.py -k expert`
- `uv run pytest bot/tests/routers/test_add_wallet.py`
- `just check-fast`
