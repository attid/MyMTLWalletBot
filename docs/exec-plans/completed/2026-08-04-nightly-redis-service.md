# nightly-redis-service: Start Redis for external nightly tests

## Context

The scheduled `External Integration` workflow has failed every day since
2026-07-12. Its two real-Redis parity tests connect to the configured
`redis://localhost:6379/0`, but the GitHub Actions job does not start Redis.
The 2026-08-04 run finished with five passing tests and two connection errors.

## Files/Directories To Change

- `.github/workflows/external-integration.yml`
- `bot/tests/external/README.md`
- `docs/exec-plans/active/2026-08-04-nightly-redis-service.md`
- `docs/exec-plans/completed/2026-08-04-nightly-redis-service.md`
- `docs/plans/2026-08-04-nightly-redis-service.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> After the assistant named `.github/workflows/external-integration.yml` and
> `bot/tests/external/README.md`, the user replied `++`.

## Change Plan

1. [x] Verify RED: the workflow has `REDIS_URL` but no Redis job service.
2. [x] Add a health-checked Redis service to the external-integration job.
3. [x] Document Redis as a requirement for the real parity tests.
4. [x] Verify the workflow structure, YAML syntax, and repository gates.
5. [x] Move the completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- Pin Redis to the current stable major instead of a floating `latest` tag.
- Do not change the test fixture to skip a missing configured dependency; that
  would hide a broken external-test environment.

## Verification

- RED/GREEN structural assertion for the Redis job service and healthcheck.
- `just check-fast`
- `git diff --check`
- Expected: Redis service is present and healthy before `just test-external`;
  repository checks pass.

Results:

- RED structural assertion failed with `external-tests has no Redis service`.
- GREEN structural assertion validated the image, port, health command, and
  retry bound.
- Real Redis parity suite against `redis:7-alpine`: `2 passed`.
- `just check-fast`: Ruff and mypy passed; `589 passed`; architecture and docs
  checks passed.
