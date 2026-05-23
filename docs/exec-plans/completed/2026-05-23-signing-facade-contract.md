# signing-facade-contract: Migrate signing confirmation contract

## Context

First migration slice for moving all user-facing XDR signing flows to
`SigningFacade`/`SignatureRequest`. This slice strengthens the shared request
contract and routes confirmation callbacks through a pending signature request,
while keeping compatibility for existing flows that still store `xdr` directly.

## Files/Directories To Change

- `bot/infrastructure/services/signing_facade.py`
- `bot/routers/sign.py`
- `bot/keyboards/common_keyboards.py`
- `bot/tests/infrastructure/test_signing_facade.py`
- `bot/tests/routers/test_sign.py`
- `docs/exec-plans/active/2026-05-23-signing-facade-contract.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add failing tests for extended `SignatureRequest` fields and stale signing
   key cleanup.
2. [x] Add failing router test that `Yes_send_xdr` can launch a pending
   signature request through the facade.
3. [x] Extend `SigningFacade` contract and add pending request helpers.
4. [x] Route `Yes_send_xdr` through pending request compatibility.
5. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Existing direct `xdr` flows must keep working until subsequent migration
  slices convert send/swap/assets/etc.
- `routers/sign.py` remains the internal legacy implementation for this slice;
  external routers will be migrated later.

## Verification

- `uv run pytest bot/tests/infrastructure/test_signing_facade.py bot/tests/routers/test_sign.py`
- `just check-fast`
- `git diff --check`
