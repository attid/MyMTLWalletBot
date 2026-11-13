# fix-secret-scan-provisioning-test: Fix gitleaks failure in CI

## Context

CI (`secrets-scan` job) failed on both `56d708b` and `5a61de4`:

```
RuleID: generic-api-key
File: bot/tests/infrastructure/test_free_wallet_provisioning.py:15
Match: MASTER_SECRET = "REDACTED"
```

The new provisioning test reused a hardcoded Stellar-looking master secret
(`S...`, 56 chars) as a dummy value. The fake stellar service never signs
anything real, so the value only needs to be a placeholder. `bot/tests/routers/test_add_wallet.py`
is allowlisted in `.gitleaks.toml`, which is why the same literal survives
there; the new file is not, and should not need an allowlist entry.

`just check`, `just test-e2e-smoke` and `just test` were green locally — the
failure is only the secret scanner, which is not part of `check-fast`.

## Files/Directories To Change

- `bot/tests/infrastructure/test_free_wallet_provisioning.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence:

> Owner reported the CI failure ("CI упал кажеться") right after the approved
> free-wallet-provisioning work; the fix stays inside the same test file.

## Change Plan

1. [x] Replace the hardcoded `S...` literal with a low-entropy placeholder and
   document why (fake signer, avoid gitleaks generic-api-key).
2. [x] Verify `just secret-scan` reports no leaks and the test still passes.
3. [x] Run `just check-fast` and `just test-e2e-smoke`.
4. [x] Move plan to completed with `just finish-task`.

## Risks / Open Questions

- Do not add `.gitleaks.toml` allowlist entries for test files: a real leaked
  key in a test path would then be silently ignored.
- Pre-existing allowlist for `test_add_wallet.py` is untouched (out of scope).

## Verification

- `just secret-scan` -> no leaks found
- `uv run pytest bot/tests/infrastructure/test_free_wallet_provisioning.py -q`
  -> 10 passed
- `just check-fast` -> 657 passed, structural checks passed
- `just test-e2e-smoke` -> 145 passed
