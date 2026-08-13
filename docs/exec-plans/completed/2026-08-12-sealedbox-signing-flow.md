# sealedbox-signing-flow: Use shared signing flow for sealed-box decryption

## Context

Sealed-box decryption currently implements its own password state and prompt.
That bypasses the shared signing flow and leaves PIN wallets without the
project-standard inline PIN keyboard.

## Files/Directories To Change

- `bot/routers/sealedbox.py`
- `bot/tests/routers/test_sealedbox.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User approved the listed paths with `++`.

## Change Plan

1. [x] Add a regression test requiring the shared PIN keyboard.
2. [x] Replace the sealed-box-specific credential prompt with `SigningFacade`.
3. [x] Continue decryption through the shared signing callback contract.
4. [x] Remove the obsolete sealed-box authentication state and handler.
5. [x] Run focused tests and `just check-fast`, then finish the plan.

## Risks / Open Questions

- The signing flow clears and rewrites FSM state while validating credentials;
  pending ciphertext and filename must survive until its continuation runs.
- WebApp wallets remain on the existing sealed-box WebApp flow and must not be
  routed into local PIN/password handling.

## Verification

- `uv run pytest bot/tests/routers/test_sealedbox.py -q`
- `just check-fast`
- Expected: PIN wallets receive `PinCallbackData` buttons, successful shared
  authentication resumes decryption, and no sealed-box password state remains.
