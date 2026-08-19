# callback-error-details: Show SEP-7 callback failure details

## Context

SEP-7 callback failures currently render only `ERROR`, so a user cannot tell
which callback failed or whether it returned an HTTP error. Show a safe callback
destination and actionable failure detail without exposing URL credentials,
query parameters, fragments, or an untrusted response body.

## Files/Directories To Change

- `bot/routers/sign.py`
- `bot/tests/routers/test_sign.py`
- `bot/langs/*.json`
- `docs/exec-plans/active/2026-08-19-callback-error-details.md`
- `docs/exec-plans/completed/2026-08-19-callback-error-details.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "ок давай" after the assistant listed `bot/routers/sign.py`,
> `bot/tests/routers/test_sign.py`, `bot/langs/*.json`, and the execution plan.

## Change Plan

1. [x] Add router tests for safe callback URL rendering, HTTP 500 details,
   generic 2xx success, and transport failure details.
2. [x] Add localized callback failure messages in `bot/langs/*.json`.
3. [x] Update `bot/routers/sign.py` to sanitize callback destinations, accept
   all 2xx statuses, and expose actionable HTTP/transport failure details.
4. [x] Run focused tests and `just check-fast`.
5. [x] Move this completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- Callback URLs may contain credentials or secrets in query parameters; only
  scheme, host, port, and path may be displayed.
- Callback bodies are untrusted and must remain out of the Telegram message.
- Existing success and return URL behavior must remain unchanged.

## Verification

- `cd bot && uv run --python /usr/bin/python3.12 --package mmwb-bot pytest -q tests/routers/test_sign.py`
- `just check-fast`
- Expected: new callback tests and existing fast checks pass.
