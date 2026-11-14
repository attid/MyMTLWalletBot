# webhook-maker-wallets-unbound: Fix UnboundLocalError maker_wallets for non-order_book trades

## Context

Webhook log (commit `4c5308e`), repeated for many operations:

```
File "/app/bot/infrastructure/services/notification_service.py", line 697,
  in process_notification
    maker_wallets=maker_wallets,
UnboundLocalError: cannot access local variable 'maker_wallets' where it is
not associated with a value
```

`maker_wallets` was assigned inside `if makers:` (inside the DB session block),
while `_send_trade_bundles(maker_wallets=maker_wallets, ...)` is called outside
it. When an operation carries `trades` but none is of type `order_book` (AMM /
liquidity-pool swaps) or has no `seller_id`, `makers` stays empty, the variable
is never bound and the webhook answers 500 — the maker bundle for that
operation is lost.

## Files/Directories To Change

- `bot/infrastructure/services/notification_service.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `docs/exec-plans/completed/2026-11-13-webhook-maker-wallets-unbound.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> да это правь

## Change Plan

1. [x] Initialize the maker/trade accumulators before the `if makers:` branch.
2. [x] Add a regression test with liquidity-pool trades (no `order_book`).
3. [x] Run `just check-fast` and `just check`.

## Risks / Open Questions

- None: the change only removes an unbound-variable path; the bundle send is
  already skipped for an empty bundle.

## Outcome (2026-11-13)

- `maker_wallets`, `maker_filters_by_user`, `maker_map`, `bundled`, `tx_hash`
  and `op_info` are initialized at the top of the `trades` branch, so an
  operation with only `liquidity_pool` fills no longer raises
  `UnboundLocalError`; `_send_trade_bundles` receives an empty bundle and
  returns without sending anything.
- Regression test covers a path-payment payload with two pool trades.

## Verification

- `uv run --package mmwb-bot pytest tests/infrastructure/test_notification_webhook.py` -> 42 passed
- `just check-fast`
- `just check`
