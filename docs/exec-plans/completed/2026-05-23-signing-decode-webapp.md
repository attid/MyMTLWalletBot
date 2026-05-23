# signing-decode-webapp: Add WebApp decode buttons to signing flow

## Context

Signing screens should let users decode the XDR without leaving or interrupting
the current signing flow. The project already stores WebApp signing transactions
in Redis and exposes `/api/tx/{tx_id}`. Reuse that storage for a WebApp decode
page, add Decode buttons to the current PIN/password/no-password/WebApp signing
screens, and keep the existing confirmation/signing sequence unchanged.

## Files/Directories To Change

- `bot/routers/sign.py`
- `bot/routers/assets.py`
- `bot/routers/send.py`
- `bot/keyboards/webapp.py`
- `bot/langs/*.json`
- `bot/tests/routers/test_sign.py`
- `bot/tests/test_signing_flow.py`
- `webapp/app.py`
- `webapp/templates/decode.html`
- `webapp/static/css/style.css`
- `webapp/static/js/i18n.js`
- `docs/exec-plans/active/2026-05-23-signing-decode-webapp.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> да вроде красиво давай так

## Change Plan

1. [x] Add WebApp decode page and route that renders a stored TX by `tx_id`.
2. [x] Add localized Decode WebApp buttons to WebApp signing keyboard.
3. [x] Lazily publish decode TX ids for non-WebApp signing screens and attach
   Decode buttons to PIN/password/no-password keyboards.
4. [x] Add `sign_msg` display support without adding an extra screen.
5. [x] Add/update bot tests and run focused tests plus `just check-fast`.

## Risks / Open Questions

- Redis may be unavailable; signing must still work without the Decode button.
- Decode must not submit or sign anything.
- Existing callback `Decode` remains for old signed-XDR screens in this slice.

## Verification

- `uv run pytest bot/tests/routers/test_sign.py bot/tests/test_signing_flow.py`
- `uv run pytest bot/tests/other/test_langs_json.py`
- `just check-fast`
- `git diff --check`
