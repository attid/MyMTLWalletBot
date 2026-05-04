# webapp-keyboard-validation: Fix webapp keyboard button validation in tests

## Context

`just check` fails in `tests/test_signing_flow.py` with
`InlineKeyboardButton` validation errors in WebApp keyboard tests. The
production keyboard code resolves `lang` correctly, but the tests create a
partial `MagicMock` app_context that does not provide a real localized string
for the shared return button, causing aiogram validation to reject the button
text.

## Files/Directories To Change

- `bot/tests/test_signing_flow.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Adjust the failing WebApp keyboard tests in `bot/tests/test_signing_flow.py` to use a valid localization mock for the shared return button.
2. [x] Re-run the narrow test selection for the three failing cases.
3. [x] Run `just check` to verify the repository gate is green again.

## Risks / Open Questions

- Keep the fix test-only unless inspection proves the production keyboard builder is wrong.

## Verification

- `uv run pytest bot/tests/test_signing_flow.py -q` -> `25 passed`
- `just check` -> passed (`594 passed, 5 deselected`)
