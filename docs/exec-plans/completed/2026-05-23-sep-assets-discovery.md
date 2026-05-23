# sep-assets-discovery: Add hidden SEP assets discovery

## Context

We are adding a hidden `/assets` entrypoint for SEP-6/SEP-24 anchor flows. The
first increment discovers which current wallet trustlines have SEP support,
caches anchor capability checks for one hour across wallets, and shows asset
conditions with action buttons. Actual SEP-10, deposit/withdraw execution, and
transaction polling will build on this discovery layer in follow-up work.

## Files/Directories To Change

- `bot/core/models/anchor_asset.py`
- `bot/infrastructure/services/anchor_discovery_service.py`
- `bot/keyboards/assets.py`
- `bot/routers/assets.py`
- `bot/start.py`
- `bot/tests/infrastructure/test_anchor_discovery_service.py`
- `bot/tests/routers/test_assets.py`
- `docs/exec-plans/active/2026-05-23-sep-assets-discovery.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add failing infrastructure tests for SEP discovery and one-hour cache by
   `(asset_code, issuer)`.
2. [x] Implement typed anchor capability models and discovery service for
   issuer `home_domain`, `stellar.toml`, SEP-6 `/info`, and SEP-24 `/info`.
3. [x] Add failing router tests for hidden `/assets` showing only SEP-supported
   trustlines and asset details/action buttons.
4. [x] Implement hidden assets router and keyboard.
5. [x] Register the router in startup.
6. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Risk: some anchors expose TOML endpoints but do not support the current asset
  in `/info`; service must check actual `/info` content.
- Risk: SEP-10 and transaction status flows are not part of this increment.
  Action buttons should be stable callback points for follow-up work.

## Verification

- `uv run pytest bot/tests/infrastructure/test_anchor_discovery_service.py bot/tests/routers/test_assets.py -q`
  - Passed: `4 passed in 1.01s`.
- `just check-fast`
  - Passed: ruff, mypy core, `404 passed`, import boundaries, docs contract,
    and exec-plan scope lock.
