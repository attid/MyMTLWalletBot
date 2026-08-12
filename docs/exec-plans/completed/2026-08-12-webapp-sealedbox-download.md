# webapp-sealedbox-download: Keep decrypted file downloadable in Telegram WebView

## Context

Browser decryption succeeds, but Telegram WebView may ignore the synthetic
download before its Blob URL is immediately revoked. The page then reports a
saved file without leaving any downloadable result.

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

1. [x] Add a failing static regression contract for a persistent download link.
2. [x] Keep the decrypted Blob URL alive and expose a visible download action.
3. [x] Update Russian and English success copy to describe the required click.
4. [x] Run focused tests and `just check-fast`.
5. [x] Finish the execution plan.

## Risks / Open Questions

- Blob data must remain browser-local and must be released when the WebView is
  closed or navigated away from.

## Verification

- `uv run pytest bot/tests/other/test_webapp_sealedbox.py -q`
- `just check-fast`
- Expected: the result remains available through a visible download link,
  plaintext is never sent to the server, and all checks pass.
