# sep10-webapp-signing: Enable SEP-10 WebApp signing

## Context

SEP `/assets` requests and SEP-24 interactive flows currently work only when the
bot can sign SEP-10 challenges with a locally available user key. Read-only
WebApp wallets (`use_pin == 10`) are blocked even though the WebApp can sign
ordinary XDRs. Add a sign-only WebApp path for SEP-10 challenge XDRs, then let
the bot exchange the signed challenge for an anchor token and continue the
original requests/deposit/withdraw flow.

## Files/Directories To Change

- `bot/routers/assets.py`
- `bot/infrastructure/services/anchor_transaction_service.py`
- `bot/infrastructure/workers/signing_worker.py`
- `bot/other/faststream_tools.py`
- `shared/src/shared/constants.py`
- `bot/tests/routers/test_assets.py`
- `bot/tests/test_signing_flow.py`
- `webapp/static/js/i18n.js`
- `webapp/templates/sign.html`
- `docs/exec-plans/active/2026-05-23-sep10-webapp-signing.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> +

## Change Plan

1. [x] Add RED tests for read-only `/assets` requests and SEP-24 actions using
   WebApp SEP-10 signing instead of the current unsupported message.
2. [x] Add RED worker tests proving signed SEP-10 challenges are exchanged for
   an anchor token and do not submit to Stellar.
3. [x] Reuse FSM `signing_purpose=sep10_auth` to represent WebApp sign-only
   SEP-10 auth requests without adding Redis fields.
4. [x] Split anchor transaction auth into challenge/exchange/token-assisted
   operations so bot and WebApp flows share protocol behavior.
5. [x] Wire `/assets` read-only flow to publish SEP-10 challenge XDR and pass
   enough metadata for the worker to continue requests/deposit/withdraw.
6. [x] Keep existing WebApp copy for now; SEP-10 context is already shown by
   the bot before opening WebApp.
7. [x] Run focused tests, `git diff --check`, and `just check-fast`.

## Risks / Open Questions

- SEP-10 challenge XDR must be sign-only; submitting it to Stellar would be
  wrong.
- Worker must preserve enough FSM context to render the final Telegram screen.
- Some anchors may return network passphrase/token errors; surface useful
  messages to users.

## Verification

- `uv run pytest bot/tests/routers/test_assets.py bot/tests/test_signing_flow.py`
- `git diff --check`
- `just check-fast`
