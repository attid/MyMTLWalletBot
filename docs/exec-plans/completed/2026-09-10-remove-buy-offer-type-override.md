# remove-buy-offer-type-override: Remove legacy buy offer type override

## Context

The notifier contract is fixed. Remove the temporary numeric-type override so
the bot uses the notifier's explicit operation type.

## Files/Directories To Change

- `bot/infrastructure/services/notification_service.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User explicitly requested removing the `type_i == 12` override.

## Change Plan

1. [x] Remove the numeric operation-type override.
2. [x] Keep corrected notifier payload coverage for buy and sell offers.
3. [x] Run targeted tests and formatting checks.

## Risks / Open Questions

- Payloads from notifier versions before 0.9.2 remain mislabeled; deployment
  ordering must ensure the notifier fix is live before this bot change.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_webhook.py`
- Ruff formatting and lint checks for touched Python files.
