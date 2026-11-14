# sep-asset-discovery-batching: SEP discovery: one anchor chain per issuer, negative cache, realistic timeouts

## Context

`/assets` did not list USDM although `https://anchor.mtlf.me/sep24/info` serves
it (`deposit`/`withdraw` enabled). Reproduction with the same code against live
mainnet data showed USDM randomly missing:

```
attempt 1: 3.00s -> ['yUSDC', 'yXLM']     # "SEP summary discovery timed out for USDM"
attempt 2: 2.00s -> ['USDM', 'yUSDC', 'yXLM']
```

Three causes, all in `AnchorDiscoveryService`:

1. Every asset of the same issuer walked the whole
   `horizon -> stellar.toml -> sep6/sep24 info` chain behind one shared URL lock,
   so with several assets the later ones queued and hit the per-asset budget.
2. The per-asset budget (3 s) was smaller than a single cold anchor `/info`
   response (measured 14.5 s on the first hit, ~1 s afterwards).
3. A failed lookup (`None`) was cached for the full one-hour TTL, so one slow
   response hid the asset for an hour with only a DEBUG log line.

## Files/Directories To Change

- `bot/infrastructure/services/anchor_discovery_service.py`
- `bot/tests/infrastructure/test_anchor_discovery_service.py`
- `docs/exec-plans/active/2026-11-13-sep-asset-discovery-batching.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ок давай Б

## Change Plan

1. [x] Group assets by issuer and resolve each anchor once
   (`discover_anchor_assets`), keeping input order.
2. [x] Raise request/summary budgets to cover a cold anchor response and log
   timeouts at WARNING.
3. [x] Cache failed lookups only for a short negative TTL.
4. [x] Add tests for grouping, per-anchor concurrency, timeout skipping and the
   negative TTL behavior.
5. [x] Run `just check-fast` and `just check`; verify against live mainnet data.

## Risks / Open Questions

- A cold anchor can make the first `/assets` slower (up to the 18 s budget);
  after that the result is cached for an hour.
- `MTL` from `mtlf.me` stays unsupported by design: the anchor's `/info` only
  serves `USDM`.

## Outcome (2026-11-13)

- `discover_assets` groups by issuer and calls `discover_anchor_assets` once per
  anchor (bounded by `list_concurrency`), then maps results back in input order.
- Budgets: `request_timeout` 3 -> 15 s, `summary_timeout` 3 -> 18 s (a cold
  anchor `/info` was measured at 14.5 s), timeouts logged at WARNING with the
  issuer and asset codes.
- `negative_ttl` (60 s) caches failed lookups briefly, so a transient anchor
  failure no longer hides an asset for the whole hour TTL.
- Live check from a cold cache now returns `['USDM', 'yUSDC', 'yXLM']` twice in
  a row (3.4 s / 3.0 s); `MTL` stays out because `mtlf.me` does not serve it.

## Verification

- `uv run --package mmwb-bot pytest tests/infrastructure/test_anchor_discovery_service.py`
- live probe: `discover_assets([USDM, MTL, yUSDC, yXLM])` twice from a cold cache
- `just check-fast`
- `just check`
