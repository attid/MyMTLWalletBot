# malformed-xdr-autodetect: Diagnose malformed XDR in global input handler

## Context

The global private-message handler auto-detects valid base64 XDR, but a malformed
XDR-like payload fails the strict base64 predicate and is silently deleted instead of
reaching the existing `bad_xdr` diagnostic.

## Files/Directories To Change

- `bot/routers/common_end.py`
- `bot/tests/routers/test_common_end.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Reproduce the reported malformed XDR in the global-message router test.
2. [x] Route clear Stellar XDR candidates through the existing XDR validator even
   when strict base64 validation fails.
3. [x] Preserve valid XDR auto-detection and ordinary-message deletion behavior.
4. [x] Run targeted tests, `just check-fast`, and `just check`.

## Risks / Open Questions

- Candidate detection must not turn arbitrary long text into a signing request.
- Parsing and user diagnostics remain owned by `cmd_check_xdr`.

## Verification

- `uv run --package mmwb-bot pytest bot/tests/routers/test_common_end.py`
- `just check-fast`
- `just check`
- The reported payload reaches `bad_xdr`; valid XDR and ordinary text retain their
  current behavior.
