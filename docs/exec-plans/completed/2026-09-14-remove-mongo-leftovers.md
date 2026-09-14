# remove-mongo-leftovers: Remove retired MongoDB leftovers (module, dep, config, infra)

## Context

MongoDB was retired from this project long ago: no production code reads or
writes it, and the only consumer (`bot/routers/mtltools.py`) was already
switched to the Grist registry check in
`docs/exec-plans/completed/2026-09-14-update-multisign-grist-check.md`.
What remains is dead weight: an unimported module, an unused dependency, an
unused setting, CI/compose env vars pointing at a database nobody uses, and
tests that only assert the dead module imports safely.

## Files/Directories To Change

- `bot/db/mongo.py` (delete)
- `bot/pyproject.toml`
- `bot/other/config_reader.py`
- `bot/tests/other/test_import_sanity.py`
- `.github/workflows/ci.yml`
- `.github/workflows/external-integration.yml`
- `.github/workflows/e2e-nightly.yml`
- `docker-compose.yml`
- `.env.template`
- `.junie/guidelines.md`
- `uv.lock` (regenerated via `uv lock`)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User approved the exact leftover list from the previous message
> (`bot/db/mongo.py`, `motor` dep, `mongodb_url` setting, mongo service in
> docker-compose, `MONGODB_URL` in three CI workflows, two tests in
> `test_import_sanity.py`, `.env.template`) with "да давай вырежим".

## Change Plan

1. [x] Deleted `bot/db/mongo.py`.
2. [x] Removed `mongodb_url` from `bot/other/config_reader.py`.
3. [x] Removed `motor~=3.6.0` from `bot/pyproject.toml`; `uv lock` dropped only `motor`, `pymongo`, `dnspython`.
4. [x] Removed the Mongo-specific tests (`test_settings_allows_missing_mongodb_url`,
   `test_db_mongo_import_is_safe_without_mongodb_url`, their helper, unused imports)
   from `bot/tests/other/test_import_sanity.py`.
5. [x] Removed `MONGODB_URL` env entries from the three GitHub workflows and
   `docker-compose.yml` (mongo service, depends_on, volume).
6. [x] Removed `MONGODB_URL` from `.env.template`; dropped both Mongo mentions in `.junie/guidelines.md`.
7. [x] Ran `just check-fast`: 448 passed (3 mongo tests + 1 parametrized module import removed); lint/mypy/arch green.

## Risks / Open Questions

- `uv lock` regeneration may bump unrelated transitive pins; keep the diff to
  motor/pymongo removal if possible.
- Deployments that still set `MONGODB_URL` in their env are unaffected: the
  setting simply stops being read.

## Verification

- `grep -ri mongo` over `bot/`, `webapp/`, `shared/`, `.github/`, `docker-compose.yml`,
  `.env.template` returns no production code references (only exec-plan history docs).
- `just check-fast` green: lint, test-fast, arch-test.
