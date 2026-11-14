# e2e-trade-swap-receive: E2E order, swap and receive routes

## Context

Closing the route list from `docs/exec-plans/completed/2026-11-14-e2e-send.md`:
place an order on the real testnet book, swap XLM into an issued asset through
the order book and render the receive screen.

## Files/Directories To Change

- `bot/tests/e2e/test_trade_swap.py` (new)
- `bot/tests/e2e/test_receive.py` (new)
- `bot/tests/e2e/conftest.py`
- `bot/tests/e2e/README.md`
- `docs/exec-plans/active/2026-11-14-e2e-trade-swap-receive.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ок го

## Change Plan

1. [x] Market fixture: issuer account quotes E2EUSD on the testnet book, trader
   gets a trustline.
2. [x] `/trade 2 XLM E2EUSD 3` → confirm → PIN → offer exists in Horizon.
3. [x] `/swap 2 XLM E2EUSD` → confirm → PIN → asset arrives on balance.
4. [x] `/receive` renders the address and QR.
5. [x] Detach the new routers between tests.
6. [x] Run the whole E2E suite, `just check-fast` and `just check`.

## Risks / Open Questions

- Each test funds 2-3 accounts via friendbot and submits 2-3 transactions, so the
  suite takes ~3 minutes and depends on testnet availability.
- The order test uses a non-crossing price (3 E2EUSD per XLM) so the offer stays
  in the book; the swap test consumes the market maker's offer.

## Outcome (2026-11-14)

- `test_trade_swap.py`: order creation verified through
  `get_selling_offers` (selling XLM, buying E2EUSD, amount 2); swap verified by
  the trader's E2EUSD balance growth.
- `test_receive.py`: the receive screen sends a QR photo whose caption contains
  the wallet address.
- Whole E2E suite: 6 tests, all green (~3 min).

## Verification

- `cd bot && HORIZON_URLS=... uv run --package mmwb-bot pytest tests/e2e -m external -q`
- `just check-fast`
- `just check`
