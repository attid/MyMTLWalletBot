# e2e-pipeline: PR smoke E2E and nightly canary scaffolding

## Context

Reduce escaped regressions by adding deterministic PR smoke E2E checks and
separate heavy integration/testnet workflows.

## Change Plan

1. [x] Add `just` recipes for smoke E2E and external test runs.
2. [x] Update PR CI workflow to require smoke E2E job.
3. [x] Add non-blocking external and nightly testnet workflows.
4. [x] Update docs/runbooks with E2E pipeline usage.
5. [x] Validate `just check-fast`, smoke E2E, and arch checks.

## Risks / Open Questions

- Smoke suite must remain deterministic and quick for PR use.
- Nightly testnet canary needs secrets; without them workflow should fail fast
  with actionable message.

## Verification

- `just check-fast` -> pass.
- `just test-e2e-smoke` -> pass.
- `just arch-test` -> pass.
