# Wallet Crypto V2 Migration

## Goal

Backfill `wallet_crypto_v2` while keeping legacy `secret_key`/`seed_key` intact
for rollback-safe Version A rollout.

## Preconditions

- Version A image is deployed (dual-read + dual-write enabled in code).
- `WALLET_KEK` is configured in runtime secrets.
- Optional: `WALLET_KEK_OLD` if key rotation fallback is needed.

## Commands

Dry-run:

```bash
just migrate-wallet-crypto-v2
```

Real migration:

```bash
just migrate-wallet-crypto-v2 args="--batch-size 200"
```

Single user verification:

```bash
just migrate-wallet-crypto-v2 args="--dry-run --user-id 123456"
```

## Expected Counters

Script prints:

- `scanned`
- `migrated`
- `skipped_has_v2`
- `skipped_missing_secret`
- `skipped_requires_user_pin`
- `skipped_decrypt_failed`
- `failed`

Notes:

- `skipped_requires_user_pin` is expected for non-free wallets with PIN/password.
- Those records migrate lazily when user successfully authenticates.

## Rollback Safety

Version A keeps writing legacy fields and does not delete them.
Old image can continue to read legacy fields during rollback window.

## Exit Criteria Before Version B

- No migration failures (`failed=0`).
- `wallet_crypto_v2` coverage is acceptable for active wallets.
- CI gates green (`just check-fast`, smoke/external suites).
