# webapp-sign-error-display: Show Stellar send errors in webapp signing flow

## Context

Web signing currently shows success immediately after the signed XDR is queued.
The actual Stellar submission happens later in `bot/infrastructure/workers/signing_worker.py`,
so Horizon failures like insufficient funds are not surfaced in the WebApp UI.
The goal of this task is to make the web signing flow wait for the final submission
result and display the same concrete send error class that the regular wallet flow
already exposes.

## Files/Directories To Change

- `webapp/app.py`
- `webapp/templates/sign.html`
- `bot/infrastructure/workers/signing_worker.py`
- `bot/routers/sign.py`
- `shared/src/shared/constants.py`
- `shared/src/shared/schemas.py` (only if a shared status payload is needed)
- `bot/tests/test_signing_flow.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Add a failing regression test in `bot/tests/test_signing_flow.py` for a WebApp-signed transaction that later fails during Stellar submission and must persist an error/result for the UI.
2. [x] Extend shared Redis status/error fields in `shared/src/shared/constants.py` and, only if needed, `shared/src/shared/schemas.py` to represent final send outcomes without guessing field names ad hoc.
3. [x] Update `bot/infrastructure/workers/signing_worker.py` and `bot/routers/sign.py` so the worker writes final success or detailed send failure back to Redis instead of deleting the transaction immediately.
4. [x] Update `webapp/app.py` and `webapp/templates/sign.html` so `/api/tx/{tx_id}` returns final status/error and the WebApp waits for completion before showing success or a concrete send error.
5. [x] Run focused tests for the signing flow, then broader lint/tests if the focused checks pass.

## Risks / Open Questions

- The current async queue design intentionally decouples signing from sending; waiting in the WebApp must not break existing bot-side callbacks or cleanup.
- Redis transaction cleanup timing changes in this task; stale keys must not accumulate on failures.
- Human-readable Horizon errors already exist in bot flow, but `submit_signed_xdr` currently sends generic chat text in some paths; the WebApp path should reuse decoded error details without widening the change unnecessarily.

## Verification

- `uv run pytest bot/tests/test_signing_flow.py -q` -> `25 passed`
- `just lint` -> `ruff check` and `mypy core` passed
- Confirmed by regression test: failed WebApp send now persists `status=error` and `error=<decoded message>` in Redis for UI polling.
