# sep-discovery-failure-classes: SEP discovery: retry/cache only transient failures, total list budget

## Context

Production log after the batching fix:

- `_fetch_with_retry` retried permanent failures: `mtlprog.xyz` toml 404,
  `horizon/accounts/GCNKX...` 404, `GDUI7...` 404 and a dead DNS name
  (`a3s.api.stellarport.io`). Each useless retry costs a second and a WARNING.
- Those permanent failures were cached for the short negative TTL (60 s), so
  every `/assets` hit them again.
- One `/assets` run held the database session for 41 seconds
  (`db.db_pool:checkin ... elapsed_seconds=40.967`) because anchor discovery
  runs inside the handler and had no overall budget.

## Files/Directories To Change

- `bot/infrastructure/services/anchor_discovery_service.py`
- `bot/routers/assets.py`
- `bot/langs/en.json`, `bot/langs/ru.json`
- `bot/tests/infrastructure/test_anchor_discovery_service.py`
- `bot/tests/routers/test_assets.py`
- `docs/exec-plans/active/2026-11-14-sep-discovery-failure-classes.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> да давай

## Change Plan

1. [x] Classify fetch failures: retry only transport errors and 5xx, never
   4xx/DNS-unknown.
2. [x] Cache permanent failures for the full TTL, transient ones for
   `negative_ttl`.
3. [x] Add a total budget for the whole list and report truncation to the user.
4. [x] Add tests.
5. [x] Run `just check-fast` and `just check`.

## Risks / Open Questions

- A permanent/transient misclassification only costs an extra request or an
  hour of a cached "unsupported" answer; both are recoverable by restart.
- Truncated lists show a localized "try again" hint instead of silently
  dropping anchors.

## Outcome (2026-11-13)

- `SepFetchError(url, status)` carries the HTTP status; `is_retryable_failure`
  retries only transport errors and 5xx, so 404 toml/horizon responses and dead
  DNS names are no longer requested twice.
- `is_permanent_failure` drives the cache lifetime: permanent failures are cached
  for the full hour TTL, transient ones for `negative_ttl` (60 s).
- `discover_assets` now has a total budget (`total_timeout`, 10 s) in addition to
  the per-anchor budget (10 s): pending anchors are cancelled, logged with their
  issuers, and `last_call_truncated` makes the router append a localized
  "try /assets again later" hint instead of silently dropping them. The handler
  no longer holds the database session for ~40 s.

## Verification

- `uv run --package mmwb-bot pytest tests/infrastructure/test_anchor_discovery_service.py tests/routers/test_assets.py`
- `just check-fast`
- `just check`
