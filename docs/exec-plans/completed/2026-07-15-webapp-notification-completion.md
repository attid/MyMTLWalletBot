# webapp-notification-completion: Complete notification flow after WebApp submit

## Context

Successful swap/send transactions signed through the WebApp are submitted by
`signing_worker`, which clears FSM state but does not complete the delayed
notification flow. The transaction's blockchain notification is therefore
queued and displayed as pending on the success screen. Local PIN signing
already completes the flow after success.

## Files/Directories To Change

- `bot/infrastructure/workers/signing_worker.py`
- `bot/tests/test_signing_flow.py`
- `docs/exec-plans/`
- `docs/plans/2026-07-15-webapp-notification-completion-design.md`
- `docs/plans/2026-07-15-webapp-notification-completion.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User answered `++` after the diagnosis named
> `bot/infrastructure/workers/signing_worker.py`,
> `bot/tests/test_signing_flow.py`, and the execution plan as the required
> change scope.

## Change Plan

1. [x] Add a RED WebApp worker regression proving successful submit completes
       the notification flow after any `fsm_after_send` callback.
2. [x] Add coverage proving a failed submit does not complete the flow.
3. [x] Call the shared best-effort completion hook in the successful normal
       WebApp send branch only.
4. [x] Run focused signing and notification tests.
5. [x] Run `just check-fast` and inspect the final diff.

## Risks / Open Questions

- Sign-only WebApp branches (`sep10_auth`, tools, callback URL, wallet connect)
  must retain their current behavior.
- Failed submissions must retain the hold so retry/error handling is not
  reclassified as a successful terminal flow.

## Verification

- RED: success case produced only `fsm_after_send` instead of the expected
  `fsm_after_send`, `complete_flow`; failure case passed.
- GREEN: `uv run pytest
  bot/tests/test_signing_flow.py::TestHandleTxSigned::test_handle_tx_signed_completes_only_successful_normal_flow
  -q` -> `2 passed`.
- Related signing/coordinator/middleware suite -> `90 passed`.
- `just check-fast` -> Ruff and Mypy clean, `548 passed`, all architecture,
  docs, and execution-plan guardrails passed.
