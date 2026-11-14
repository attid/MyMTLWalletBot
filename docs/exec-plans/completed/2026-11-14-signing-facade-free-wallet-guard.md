# signing-facade-free-wallet-guard: Enforce free-wallet XLM policy in SigningFacade

## Context

The E2E send slice proved that a free wallet (`is_free=True`) can spend native
XLM through `/send`: the ADR-0003 policy ran only inside `cmd_check_xdr`
(pasted XDR, URI, sign_tools), while every wizard — send, swap, trade, cheque,
SEP-10 sign-only, WebApp publishing — signs through `SigningFacade`, which
stored the request and asked for a PIN without any check.

## Files/Directories To Change

- `bot/infrastructure/services/signing_facade.py`
- `bot/tests/infrastructure/test_signing_facade.py`
- `bot/tests/e2e/test_send.py`
- `bot/tests/e2e/README.md`
- `docs/exec-plans/active/2026-11-14-signing-facade-free-wallet-guard.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> да чини

## Change Plan

1. [x] Run the free-wallet XDR policy inside `SigningFacade.request_signature`
   (and therefore for pending signature requests too).
2. [x] On `FreeWalletPolicyError` clear the flow, show the localized
   `bad_xdr_free_wallet` message and return `SignatureStatus.REJECTED` without
   prompting for a PIN.
3. [x] Use the checked XDR (policy may rewrite `eurmtl.me/sign_tools` links).
4. [x] Add unit tests and un-xfail the E2E case.
5. [x] Run `just check-fast`, `just check` and the E2E suite.

## Risks / Open Questions

- `check_xdr` returns None for payloads it cannot parse (for example an XDR for
  another network); the facade then keeps the original XDR so downstream keeps
  its existing error reporting.
- A failed free-wallet lookup is treated as not-free (same as `cmd_check_xdr`),
  because blocking every signing flow on a DB hiccup would be worse; the
  operation-level check still fails closed for native XLM.

## Outcome (2026-11-14)

- `SigningFacade.request_signature` resolves the free-wallet state, runs
  `check_xdr(..., for_free_account=True, free_wallet_public_key=...)` and either
  signs the checked XDR or rejects with a localized message.
- Unit tests cover rejection, rewritten XDR and the non-free fast path.
- E2E: free wallet no longer moves XLM (`0.00` balance change) and the user sees
  the policy message; the marker `xfail` was removed.

## Verification

- `uv run --package mmwb-bot pytest tests/infrastructure/test_signing_facade.py` -> 7 passed
- `pytest tests/e2e -m external -q` -> 3 passed (~77 s)
- `just check-fast`, `just check`
