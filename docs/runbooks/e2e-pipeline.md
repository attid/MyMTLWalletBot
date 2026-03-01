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

## Nightly Inputs

- No mandatory secrets for baseline canary.
- Optional env overrides:
  - `HORIZON_TESTNET_URL` (default: `https://horizon-testnet.stellar.org`)
  - `FRIENDBOT_URL` (default: `https://friendbot.stellar.org`)

Nightly canary creates a fresh account via Friendbot and verifies it through
Horizon.
