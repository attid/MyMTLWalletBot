# fix-manage-buy-offer-notification: Map manage buy offer notification payload correctly

## Context

The notifier previously labeled `manageBuyOffer` payloads as
`manage_sell_offer` even though `type_i` remained `12`. After the notifier fix,
the canonical buy-offer payload still uses the shared `asset` and
`source_asset` fields. The bot must map both the corrected payload and legacy
in-flight payloads without swapping bought and sold assets.

## Files/Directories To Change

- `bot/infrastructure/services/notification_service.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User replied `++` after the exact paths were listed.

## Change Plan

1. [x] Normalize legacy `type_i=12` payloads to `manage_buy_offer`.
2. [x] Map canonical `asset`/`source_asset` fields with legacy field fallback.
3. [x] Add regression coverage for corrected buy offers, legacy mislabeled buy
   offers, and unaffected sell offers.
4. [x] Confirm translations require no contract changes.
5. [x] Run targeted tests, `just check-fast`, and `just check`.

## Risks / Open Questions

- During a rolling notifier deployment, both old and corrected payloads may be
  delivered; `type_i` is the stable discriminator.
- A sell offer must remain a sell offer when `type_i=3`.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_webhook.py`
- `just check-fast`
- `just check`
- Expected: all mapping assertions and repository gates pass.
