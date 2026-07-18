# remove-fest: Remove dormant Fest feature and dependencies

## Context

Fest is disabled and will not be used for approximately one year. Keeping its
season-specific router and tests active creates maintenance failures without
user value. Remove it from the runtime; Git remains the source for any future
restoration under a new specification.

## Files/Directories To Change

- `bot/routers/fest.py`
- `bot/tests/routers/test_fest.py`
- `bot/start.py`
- `bot/other/config_reader.py`
- `bot/other/grist_tools.py`
- `bot/other/gspread_tools.py`
- `bot/pyproject.toml`
- `uv.lock`
- `docs/exec-plans/active/2026-07-18-remove-fest.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++"

## Change Plan

1. [x] Remove the Fest router, its registration, configuration, and dedicated
   tests.
2. [x] Remove Fest-only Grist/Google Sheets loaders and the now-unused
   `gspread-asyncio` dependency.
3. [x] Regenerate the uv lockfile and verify no Fest/gspread runtime references
   remain.
4. [x] Run focused import checks, full tests, and repository gates.
5. [x] Move this plan to completed after verification.

## Risks / Open Questions

- Removing a dependency must not remove Google auth packages still required by
  another integration; the regenerated lockfile decides transitive retention.
- Historical restoration must use Git rather than a dormant copy in the source
  tree.

## Verification

- `rg -n -i 'fest|gspread' bot --glob '*.py' --glob '*.toml'`
- `uv lock`
- `just test`
- `just check-fast`
- `just test-e2e-smoke`
- `git diff --check`
- Expected: no active Fest/gspread references and all relevant checks pass,
  except any separately documented pre-existing failures.

Verification evidence:

- `uv lock`: removed `gspread-asyncio` and 9 now-unused transitive packages.
- Active-reference audit: only the unrelated recommended Stellar asset
  `MTLFEST` remains; no Fest router/config/loader or gspread reference remains.
- Full `just test`: Fest failure removed; `852 passed`, with only the 2
  pre-existing MTLTools failures remaining.
- `just check-fast`: Ruff, Mypy, architecture/docs checks passed; `546 passed`.
- `just test-e2e-smoke`: `117 passed`.
- Focused Ruff format check and `git diff --check`: passed.
