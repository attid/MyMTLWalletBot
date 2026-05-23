# assets-inout-signing-facade: Migrate assets and inout signing

## Context

Next migration slice for moving user-facing XDR signing to
`SigningFacade`/`SignatureRequest`. SEP assets currently call `PinState` and
`cmd_ask_pin` directly. USDT in/out stores loose XDR and `fsm_after_send`;
this slice should route both through explicit signature requests while
preserving compatibility fields during the larger migration.

## Files/Directories To Change

- `bot/routers/assets.py`
- `bot/routers/inout.py`
- `bot/tests/routers/test_assets.py`
- `bot/tests/routers/test_inout.py`
- `docs/exec-plans/active/2026-05-23-assets-inout-signing-facade.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> +++

## Change Plan

1. [x] Add failing tests for assets SEP auth using `SigningFacade`.
2. [x] Add/update inout tests for pending `SignatureRequest` and USDT recipient
   state preservation.
3. [x] Migrate assets SEP-10 auth to `SigningFacade.request_signature`.
4. [x] Migrate inout signing setup to store pending `SignatureRequest`.
5. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- USDT out originally lost destination data after signing; keep recipient state
  explicit and covered by tests.
- Keep legacy fields until all downstream signing code is migrated.

## Verification

- `uv run pytest bot/tests/routers/test_assets.py bot/tests/routers/test_inout.py`
- `just check-fast`
- `git diff --check`
