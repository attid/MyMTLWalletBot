# back-home-labels: Distinguish Back and Home button labels

## Context

The new flow-local Back action and the global Return/Home action currently use
labels that both mean "Back". Keep callback behavior unchanged while making the
UI semantics explicit in every supported locale. Notification Return buttons
must also display Home.

## Files/Directories To Change

- `bot/langs/am.json`
- `bot/langs/en.json`
- `bot/langs/hy.json`
- `bot/langs/me.json`
- `bot/langs/ru.json`
- `bot/langs/ua.json`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `docs/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++"

Additional permission for the notification webhook test path:

> "++"

## Change Plan

1. [x] Set `kb_back` to a localized Back label and `kb_return` to a localized
   Home label in all supported locale files.
2. [x] Preserve callback identifiers and all routing/notification behavior.
3. [x] Run language validation, focused navigation tests, and repository gates.

## Risks / Open Questions

- Translation files must retain identical key sets and valid JSON.

## Verification

- All supported language JSON files retain matching key sets and valid labels.
- Notification messages retain the legacy Settings + Return callback behavior;
  Return now displays the localized Home label.
- Focused FlowBack router regressions: `21 passed`.
- `just check-fast`: passed, including `546 passed`, Ruff, core mypy,
  architecture, docs-contract, and scope-lock checks.
- `just test-e2e-smoke`: `117 passed`.
- `just test-external`: `7 passed`.
- `just secret-scan`: passed; no leaks found.
- Independent Terra final review: `APPROVE`.
