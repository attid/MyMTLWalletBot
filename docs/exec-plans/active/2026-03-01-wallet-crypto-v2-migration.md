# wallet-crypto-v2-migration: Wallet crypto v2 with dual-format transition

## Context

Need to harden wallet secret storage against a "DB-only leak" threat model,
without breaking the core product behavior:

- free wallets (NoPassword) are mandatory and must remain controllable by system;
- non-free wallets must decrypt only with user PIN/password;
- TON wallets must not break;
- migration and rollback must stay operationally safe.

Operational rollout without feature flags:

- Version A (transition): read/write both formats.
- One week later, Version B: v2-only reads/writes.
- One more week later: manual DB cleanup of legacy columns.

## Files/Directories To Change (Version A)

- `bot/db/models.py`
- `bot/core/domain/entities.py`
- `bot/infrastructure/persistence/sqlalchemy_wallet_repository.py`
- `bot/infrastructure/services/encryption_service.py`
- `bot/core/use_cases/wallet/get_secrets.py`
- `bot/core/use_cases/wallet/change_password.py`
- `bot/core/use_cases/wallet/add_wallet.py`
- `bot/infrastructure/services/wallet_secret_service.py`
- `bot/other/stellar_tools.py`
- `bot/routers/add_wallet.py`
- `bot/routers/ton.py` (only if adapter updates are needed)
- `bot/scripts/` (new migration script)
- `bot/tests/infrastructure/test_encryption_service.py`
- `bot/tests/core/test_get_wallet_secrets_with_seed.py`
- `bot/tests/routers/test_add_wallet.py`
- `bot/tests/routers/test_ton.py`
- `bot/tests/external/` (if canary updates are needed)
- `adr/` (new ADR)
- `docs/runbooks/` (migration/rollback runbook)

## Change Plan

1. [ ] Add new DB field and model mapping (no legacy removal).
   - Add `wallet_crypto_v2` (`Text`/CLOB) to wallet table model in
     `bot/db/models.py`.
   - Add corresponding field to domain entity in `bot/core/domain/entities.py`.
   - Update create/read/update mappings in
     `bot/infrastructure/persistence/sqlalchemy_wallet_repository.py`.
   - Keep legacy columns `secret_key` and `seed_key` intact.

2. [ ] Introduce v2 crypto container format in one field.
   - Store JSON container in `wallet_crypto_v2`.
   - Required metadata:
     - `v` (2),
     - `wallet_kind` (`stellar_free`, `stellar_user`, `ton_free`),
     - `mode` (`free` or `user`),
     - `kid` (`current` or `old`),
     - `salt` (base64 random),
     - `secret` block: `{nonce, ct}`,
     - optional `seed` block: `{nonce, ct}`.
   - Keep `seed` separate from `secret` to avoid decrypting seed in normal flows.

3. [ ] Implement encryption/decryption primitives in `EncryptionService`.
   - Extend legacy flow with v2 methods for free and user modes.
   - Use Argon2id for user-mode key derivation.
   - Use AEAD cipher (AES-GCM or ChaCha20-Poly1305).
   - Use random `salt` and random `nonce`.
   - Key inputs (simple config):
     - `WALLET_KEK` (required),
     - `WALLET_KEK_OLD` (optional, for rotation window).
   - Writes always use `kid=current`; reads may fallback to `old`.

4. [ ] Update read paths to prefer v2 with legacy fallback.
   - If `wallet_crypto_v2` exists and is valid, use it.
   - Otherwise fallback to legacy `secret_key/seed_key`.
   - Cover:
     - `bot/core/use_cases/wallet/get_secrets.py`,
     - `bot/other/stellar_tools.py`,
     - any direct secret usage discovered during implementation.

5. [ ] Update write paths for Version A dual-write compatibility.
   - On create/update/password change:
     - always write `wallet_crypto_v2`,
     - and keep legacy `secret_key/seed_key` updated.
   - This guarantees rollback to old image remains functional.
   - Cover free, non-free, and TON create/update flows.

6. [ ] TON compatibility adaptation (must not break).
   - Current TON detection relies on `secret_key == "TON"` and mnemonic in
     `seed_key`.
   - For Version A:
     - keep legacy TON fields updated (dual-write),
     - write v2 representation (`wallet_kind=ton_free`) in parallel.
   - Update `wallet_secret_service` read logic:
     - v2 first,
     - legacy fallback.
   - Verify `routers/ton.py` user flows are unchanged.

7. [ ] Add migration script (safe and idempotent).
   - Create script in `bot/scripts/` to backfill `wallet_crypto_v2`.
   - Script behavior:
     - scan wallets with empty v2,
     - migrate legacy to v2,
     - keep legacy untouched,
     - support dry-run and batch/chunk execution.
   - Track counters: migrated/skipped/failed.

8. [ ] Add robust tests.
   - Infra tests (`test_encryption_service.py`):
     - free/user roundtrip,
     - wrong PIN fails,
     - tampered ciphertext fails,
     - old-key fallback works.
   - Core tests (`test_get_wallet_secrets_with_seed.py`):
     - v2 secret-only read,
     - seed decrypted only when requested,
     - legacy fallback.
   - Router tests:
     - add-wallet NoPassword/PIN/password branches,
     - TON wallet create/send branch.
   - Migration tests:
     - legacy -> v2 idempotency,
     - dual-write correctness.

9. [ ] Add docs and ADR.
   - New ADR: wallet crypto v2 design + threat model + rollout/rollback.
   - New/updated runbook: migration steps, validation checklist,
     rollback behavior.

10. [ ] Verify Version A readiness and rollback safety.
    - Confirm old image can read wallets created by Version A.
    - Confirm Version A can read both legacy and v2 records.
    - Confirm no regressions in CI gates.

## Version B Plan (scheduled, not in same PR)

1. [ ] Remove legacy read fallback from code (v2-only reads).
2. [ ] Stop legacy writes (v2-only writes).
3. [ ] Keep DB legacy columns temporarily for safety window.
4. [ ] Run full regression and canary.
5. [ ] After one more week and validation, execute manual DB cleanup:
   - drop `secret_key` and `seed_key`.

## Risks / Open Questions

- Risk: TON compatibility break due to legacy assumptions.
  - Mitigation: dual-read + dual-write in Version A and dedicated TON tests.
- Risk: mixed record population during migration.
  - Mitigation: idempotent migration script with counters and reruns.
- Risk: rollback incompatibility for newly created wallets.
  - Mitigation: strict dual-write in Version A.
- Open question: production DDL syntax details for target Firebird environment.

## Verification

- Baseline commands:
  - `just lint`
  - `just check-fast`
  - `just test-e2e-smoke`
  - `just test-external`
- Targeted checks:
  - wallet crypto v2 unit/integration tests,
  - TON router tests,
  - send/sign password flows.
- Operational checks:
  - migration dry-run and real run,
  - total wallets vs v2-populated wallets,
  - rollback drill: create wallet in Version A, validate old image read path.
