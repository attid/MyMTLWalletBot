# E2E Pipeline

## Goal

Catch user-flow regressions before merge while keeping PR feedback fast.

## Layers

1. **PR deterministic gate**
   - `just check-fast`
   - `just test-e2e-smoke`
2. **External integration (scheduled/manual)**
   - `just test-external`
3. **Nightly testnet canary**
   - `.github/workflows/e2e-nightly.yml`

## Smoke Scope

`just test-e2e-smoke` runs critical router flows with mock Telegram and mock
Horizon to validate end-to-end user interactions without flaky external calls.

## Required Nightly Secrets

- `TESTNET_MASTER_PUBLIC_KEY`
- `TESTNET_MASTER_SECRET_KEY`
- `HORIZON_TESTNET_URL` (optional override)

Nightly workflow fails fast if mandatory secrets are missing.
