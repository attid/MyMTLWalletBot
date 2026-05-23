# send-swap-signing-facade: Migrate send and swap signing confirmations

## Context

Second migration slice for moving user-facing XDR signing to
`SigningFacade`/`SignatureRequest`. `/send` and `swap` should keep their current
confirmation screens, but those screens must store a pending `SignatureRequest`
instead of relying only on loose FSM `xdr` fields.

## Files/Directories To Change

- `bot/routers/send.py`
- `bot/routers/swap.py`
- `bot/tests/routers/test_send.py`
- `bot/tests/routers/test_swap.py`
- `docs/exec-plans/active/2026-05-23-send-swap-signing-facade.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add failing send router test for pending `SignatureRequest`.
2. [x] Add failing swap router tests for pending `SignatureRequest`.
3. [x] Store pending signature request in `/send` confirmation flow.
4. [x] Store pending signature request in all swap confirmation flows.
5. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Keep legacy loose `xdr` fields during this slice for compatibility until all
  flows and tests no longer depend on them.
- Preserve current confirmation keyboards and callback data.

## Verification

- `uv run pytest bot/tests/routers/test_send.py bot/tests/routers/test_swap.py`
- `just check-fast`
- `git diff --check`
