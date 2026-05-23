# sep-assets-light-discovery: Avoid SEP info probes on assets list

## Context

The initial hidden `/assets` discovery probed SEP-6/SEP-24 `/info` for every
asset. Wallets with many trustlines sharing a slow/dead anchor could block for
minutes and keep DB sessions open. The list view should only check issuer
`home_domain` and `stellar.toml`; expensive `/info` calls are deferred until the
user opens a specific asset.

## Files/Directories To Change

- `bot/core/models/anchor_asset.py`
- `bot/infrastructure/services/anchor_discovery_service.py`
- `bot/routers/assets.py`
- `bot/keyboards/assets.py`
- `bot/tests/infrastructure/test_anchor_discovery_service.py`
- `bot/tests/routers/test_assets.py`
- `AGENTS.md`
- `docs/exec-plans/active/2026-05-23-sep-assets-light-discovery.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> нет предлагю не трогать /sep6/info /sep24/info пока не зайдем внутрь ассета

> ++

## Change Plan

1. [x] Add regression coverage that `/assets` list discovery does not call
   `/sep6/info` for assets sharing an issuer.
2. [x] Split lightweight issuer/TOML discovery from full per-asset `/info`
   discovery.
3. [x] Keep full `/info` discovery for asset detail conditions.
4. [x] Add short default HTTP timeout around anchor discovery requests.
5. [x] Use the project message helper in `/assets` so inline buttons update
   `last_message_id` and are not rejected as old buttons.
6. [x] Document the router inline keyboard rule in `AGENTS.md`.
7. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- List view may now show assets from anchors that expose SEP endpoints in TOML
  but do not support that specific asset in `/info`. The detail view remains the
  authoritative check and will show support only when `/info` confirms it.

## Verification

- `uv run pytest bot/tests/infrastructure/test_anchor_discovery_service.py bot/tests/routers/test_assets.py -q`
  - `7 passed in 1.61s`
- `uv run ruff check bot/core/models/anchor_asset.py bot/infrastructure/services/anchor_discovery_service.py bot/routers/assets.py bot/keyboards/assets.py bot/tests/infrastructure/test_anchor_discovery_service.py bot/tests/routers/test_assets.py`
  - `All checks passed!`
- `uv run ruff format --check bot/core/models/anchor_asset.py bot/infrastructure/services/anchor_discovery_service.py bot/routers/assets.py bot/keyboards/assets.py bot/tests/infrastructure/test_anchor_discovery_service.py bot/tests/routers/test_assets.py`
  - `6 files already formatted`
- `just check-fast`
  - `ruff check .`: `All checks passed!`
  - `mypy core`: `Success: no issues found in 27 source files`
  - `pytest tests/core tests/infrastructure tests/other -m "not integration"`:
    `405 passed in 5.67s`
  - `check_import_boundaries.py`: `Import boundary checks passed.`
  - `check_docs_contract.py`: `Docs contract checks passed.`
  - `check_exec_plan_scope_lock.py`: `Execution plan scope-lock checks passed.`
