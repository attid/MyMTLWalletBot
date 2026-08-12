# ghcr-publish: Publish bot and webapp images to GHCR

## Context

Images are currently published only by a local `just push-gitdocker` command.
GitHub CI must publish both runtime images under the repository owner's GHCR
namespace after every successful push to `main`.

## Files/Directories To Change

- `.github/workflows/ci.yml`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> `++`

## Change Plan

1. [x] Add a gated GHCR publish job for bot and WebApp images.
2. [x] Restrict publishing to successful pushes on `main`.
3. [x] Validate workflow syntax and repository architecture checks.

## Risks / Open Questions

- An older concurrent run must not overwrite `latest` after a newer run, so
  image publication uses a cancel-in-progress concurrency group.
- Pull requests must never receive package write access or publish images.

## Verification

- `actionlint .github/workflows/ci.yml` passes.
- `just arch-test` passes.
- Manual review confirms both Dockerfiles and both requested GHCR tags.

Final results:

- `actionlint .github/workflows/ci.yml`: passed.
- `just arch-test`: passed.
- Local bot and WebApp Docker builds: passed.
- Matrix concurrency is isolated per image so bot and WebApp builds do not
  cancel each other.
