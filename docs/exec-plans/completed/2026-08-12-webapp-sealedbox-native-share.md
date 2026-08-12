# webapp-sealedbox-native-share: Export decrypted files from Telegram WebView

## Context

Telegram WebView ignores downloads backed by browser-local `blob:` URLs, even
when the user clicks a persistent link. Export the already decrypted bytes via
the device-native Web Share API while keeping plaintext local to the browser.

## Files/Directories To Change

- `webapp/static/js/sealedbox.js`
- `webapp/templates/sealedbox.html`
- `webapp/static/js/i18n.js`
- `bot/tests/other/test_webapp_sealedbox.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User approved the listed paths with `++`.

## Change Plan

1. [x] Add a failing regression contract for `File` plus native file sharing.
2. [x] Replace the visible Blob link with a button invoking `navigator.share`.
3. [x] Display locally decrypted text and provide a browser-download fallback.
4. [x] Update Russian and English UI copy.
5. [x] Run focused tests and `just check-fast`, then finish the plan.

## Risks / Open Questions

- Native sharing requires a direct user gesture; only the explicit result
  button may invoke it.
- Plaintext must never be uploaded to the app server.

## Verification

- `uv run pytest bot/tests/other/test_webapp_sealedbox.py -q`
- `just check-fast`
- Expected: the result is represented as a local `File`, native file sharing is
  available from a button, text is rendered locally, and no plaintext appears
  in requests.
