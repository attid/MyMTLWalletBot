# docker-test-image: Isolated test runner image

## Context

The user requested a separate Dockerfile to run the bot tests without installing Python, uv, just, or project packages on the host. The production Dockerfile installs with `--no-dev`, so it cannot run pytest as built.

## Files/Directories To Change

- `Dockerfile.test`
- `.dockerignore`
- `docs/exec-plans/active/2026-09-29-docker-test-image.md`
- `docs/exec-plans/completed/2026-09-29-docker-test-image.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence: User asked `создай отдельный докер файл для прогонки тестов`. `Dockerfile.test` implements the request; `.dockerignore` prevents local `.env` files from entering its build context.

## Change Plan

1. [x] Add a test image with locked bot and dev dependencies and required system libraries.
2. [x] Provide non-secret test configuration and default command for local tests without external integrations.
3. [x] Exclude local `.env` files from the Docker context.
4. [x] Verify Dockerfile structure and scope; document that image build cannot be run on this host.

## Risks / Open Questions

- Docker CLI/daemon are unavailable on this host, so container build and test execution cannot be verified here.
- External integration tests require additional services and are excluded by default.

## Verification

- Inspect Dockerfile stages, locked dependency installation, and test command.
- Run available documentation/scope checks and `git diff --check`.
- When Docker is available: `docker build -f Dockerfile.test -t mmwb-tests .`, then `docker run --rm mmwb-tests`.

Static checks on 2026-09-29: documentation contract, execution-plan scope lock,
and `git diff --check` passed. Docker CLI was not found in PATH or its common
Windows install location, so the image build and test command remain unverified.
