# webapp-chat-send-error: Restore webapp close behavior and show send errors in bot chat

## Context

Previous implementation incorrectly changed the WebApp UI flow to wait for
network submission results. The intended behavior is unchanged WebApp UX:
sign and close immediately. The actual fix should be in the bot flow after
WebApp signing, so the user sees the same detailed send error in chat that a
regular wallet send already shows.

## Files/Directories To Change

- `bot/routers/sign.py`
- `bot/infrastructure/workers/signing_worker.py`
- `webapp/app.py`
- `webapp/templates/sign.html`
- `webapp/static/js/i18n.js`
- `shared/src/shared/constants.py`
- `bot/tests/test_signing_flow.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Replace the WebApp-oriented regression in `bot/tests/test_signing_flow.py` with a bot chat regression that requires detailed Horizon send errors to be included in the Telegram message after WebApp signing.
2. [x] Update `bot/routers/sign.py` so `submit_signed_xdr()` sends the same detailed send error text to chat for Horizon failures instead of only the generic localized header.
3. [x] Revert the unintended WebApp waiting/polling changes in `webapp/app.py`, `webapp/templates/sign.html`, `webapp/static/js/i18n.js`, and any no-longer-needed shared/worker status plumbing.
4. [x] Keep `bot/infrastructure/workers/signing_worker.py` aligned with the original WebApp contract: queue, process, notify in chat, then clean up.
5. [x] Run focused tests and lint for the touched backend paths.

## Risks / Open Questions

- The bot has multiple send flows with slightly different error formatting; this fix should improve the WebApp-post-sign path without broad refactoring.
- Reverting the WebApp polling changes must not break the existing successful close-on-sign behavior.

## Verification

- `uv run pytest bot/tests/test_signing_flow.py -q` -> `25 passed`
- `just lint` -> `ruff check` and `mypy core` passed
- Confirmed by regression test that chat-side send error now contains both the localized `send_error` header and the decoded Horizon reason.
