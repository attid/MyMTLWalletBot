# wallet-pin-prompt-after-import: Fix PIN prompt after expert key import

## Context

After importing a wallet with "I have a key", the FSM data keeps the previous
`send_key` prompt in `msg`. When the user chooses PIN protection, `cmd_ask_pin`
reuses that stale text and shows the private-key prompt above the PIN keyboard.

## Files/Directories To Change

- `bot/routers/add_wallet.py`
- `bot/tests/routers/test_add_wallet.py`
- `docs/exec-plans/active/2026-05-14-wallet-pin-prompt-after-import.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add a regression test for Have Key -> send key -> PIN prompt.
2. [x] Clear or replace stale FSM `msg` after successful key import.
3. [x] Verify existing key import and PIN state behavior remain intact.
4. [x] Run focused tests and fast gate.

## Risks / Open Questions

- Keep the fix scoped to bot wallet import; do not touch webapp behavior.

## Verification

- `uv run pytest bot/tests/routers/test_add_wallet.py -k pin_prompt -q`
- `uv run pytest bot/tests/routers/test_add_wallet.py -q`
- `just check-fast`
