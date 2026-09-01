# grist-cutover: Audited Grist cutover

## Context

Replace the audited Montelibero/GetGrist document bindings with their confirmed
EURMTL Grist counterparts while keeping Grist access centralized and secrets
runtime-only. No RELY binding is present in this repository and none will be
added.

## Files/Directories To Change

- `bot/other/config_reader.py`
- `bot/other/grist_tools.py`
- `bot/tests/other/test_grist_tools.py`
- `docker-compose.yml`
- `.env.template`
- `.gitignore`
- `docs/exec-plans/active/2026-08-31-grist-cutover.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> Approved exactly as stated. Proceed now. No RELY additions in mmwb_bot.
>
> Approve .gitignore. Add all required Codespaces generated-map entries without
> removing or rewriting existing rules.
>
> Approve .env.template for the same non-secret GRIST_BASE_URL example. Do not
> add secret values.

## Change Plan

1. [x] Add the new centralized Montelibero Grist root and update every mapped
   dormant/active document binding in `bot/other/grist_tools.py`.
2. [x] Keep any RELY host/credential path separate if discovered (none expected).
3. [x] Add deterministic tests covering root, all mapped IDs, and no secret values.
4. [x] Update the Compose and `.env.template` configuration examples and required
   Codespaces ignore entries.
5. [x] Run focused tests, lint, architecture checks, and secret scan.

## Risks / Open Questions

- Runtime deployments still need `GRIST_TOKEN` supplied through their secret
  manager; no token is added to source or examples.
- External Grist services must not be called during local verification.

## Verification

- `uv run pytest bot/tests/other/test_grist_tools.py`
- `just lint`
- `just arch-test`
- `just secret-scan`

Results: focused Grist tests passed (21 tests); `just test-fast` passed (443
tests); lint, architecture checks, and secret scan passed. No external Grist
service was contacted.
