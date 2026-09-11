# fix-trade-offer-fill-notification: Fix inverted trade direction and add offer link for offer-fill notifications

## Context

User complaint from account `GBYH3M3REQM3WQOJY26FYORN23EXY22FWBHVZ74TT5GYOF22IIA7YSOX`:
the offer-fill notification is unreadable ("не понятно что тут").

Root causes verified with a testnet experiment (crossing manage_sell_offer) and a
simulation of the bot code on the real payload:

- In `ClaimOfferAtom` (and therefore the notifier `operation.trades` payload),
  `seller_id` is the offer owner, `amount_sold` is what the owner GAVE and
  `amount_bought` is what the owner RECEIVED.
- The `trade` branch of `decode_db_effect` feeds the shared `info_trade` template
  with `(bought, sold)`, while the phrase "X was exchanged for Y" / «обменено X
  на Y» means "gave X, received Y" — so the maker sees the trade direction
  inverted.
- The message does not explain WHY the trade happened (the user's own resting
  offer was executed), which is the main source of confusion.
- The claim atom carries the maker's `offer_id` (already emitted by the notifier)
  but the bot drops it; a viewer offer link would identify the order.

Own swaps (`path_payment_*`) and own order placement (`info_sell_offer`) are NOT
affected: they use different branches with the correct parameter order.

## Files/Directories To Change

- `bot/infrastructure/services/notification_service.py`
- `bot/infrastructure/utils/notification_utils.py`
- `bot/langs/en.json`
- `bot/langs/ru.json`
- `bot/langs/ua.json`
- `bot/langs/me.json`
- `bot/langs/am.json`
- `bot/langs/hy.json`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User: «Даёшь добро на эти пути?» → «да давай»
> (after the offer-link question: «ссылку на офер на вьювер сможем вставить?» was
> answered with the file list including `notification_service.py`)

## Change Plan

1. [x] Maker loop (`_process_notification` trades section): propagate
   `offer_id` from the trade payload into `op_trade.offer_id`.
2. [x] `decode_db_effect` `trade` branch: switch to a new `info_trade_filled`
   localization key with parameters `(account_link, sold_amount, sold_asset,
   bought_amount, bought_asset, offer_id_text, op_link)` and a viewer offer link
   when `offer_id > 0`.
3. [x] Add `info_trade_filled` to all six language files (en/ru/ua/me/am/hy).
4. [x] Add regression tests: maker trade direction (sold→bought), offer link
   presence/absence, and that `info_trade` path-payment output is unchanged.
5. [x] Run targeted tests, `just check-fast`, `just check`.

## Risks / Open Questions

- Legacy trade payloads without `offer_id`: link is omitted gracefully (empty
  `offer_id_text`), message stays valid.
- `info_trade` template stays for `path_payment_*` only; no other callers exist.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_webhook.py`
- `just check-fast`
- `just check`
- Expected: all gates pass; new assertions cover direction and offer link.
