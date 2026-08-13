# sealedbox-text-relay-command: Complete sealed-box text and relay flows

## Context

Complete the sealed-box UX with direct `/crypto` entry, text ciphertext input,
recipient-aware prompts, compact single-message encryption results, and an
explicit server relay fallback for Telegram WebViews that cannot export files.

## Files/Directories To Change

- `bot/start.py`
- `bot/routers/sealedbox.py`
- `bot/infrastructure/workers/sealedbox_worker.py`
- `bot/langs/ru.json`
- `bot/langs/en.json`
- `webapp/app.py`
- `webapp/static/js/sealedbox.js`
- `webapp/static/js/i18n.js`
- `webapp/templates/sealedbox.html`
- `shared/src/shared/constants.py`
- `shared/src/shared/schemas.py`
- `shared/src/shared/__init__.py`
- `bot/tests/routers/test_sealedbox.py`
- `bot/tests/other/test_webapp_sealedbox.py`
- `bot/tests/other/test_startup_wiring.py`
- `bot/tests/test_sealedbox_webapp_flow.py`
- `docs/plans/`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User approved the full list and `/crypto` addition with “ок давай”.

## Change Plan

1. [x] Add failing tests for `/crypto`, recipient prompt, Base64 input, and
   compact document captions.
2. [x] Implement the bot command and text encryption/decryption UX.
3. [x] Add failing endpoint and worker tests for optional plaintext relay.
4. [x] Implement owner-bound, TTL-limited Redis relay and Telegram delivery.
5. [x] Update WebApp fallback UI and Russian/English localization.
6. [x] Run focused suites, `just check-fast`, and finish the plan.

## Risks / Open Questions

- Telegram document captions are limited to 1024 characters; include Base64
  only when the fully formatted caption fits.
- Plaintext relay is opt-in, capped at 10 MB, TTL-bound, never logged, and
  removed immediately after successful Telegram delivery.

## Verification

- `uv run pytest bot/tests/routers/test_sealedbox.py bot/tests/other/test_webapp_sealedbox.py bot/tests/test_sealedbox_webapp_flow.py bot/tests/other/test_startup_wiring.py -q`
- `just check-fast`
- Expected: all sealed-box flows and repository gates pass.
