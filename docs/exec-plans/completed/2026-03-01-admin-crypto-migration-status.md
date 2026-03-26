# admin-crypto-migration-status: Admin command for crypto v2 migration progress

## Context

Need an admin-visible command to show how many wallets are not yet migrated to
`wallet_crypto_v2`, with a compact breakdown useful during rollout.

## Files/Directories To Change

- `bot/routers/admin.py`
- `bot/tests/routers/test_admin.py`
- `docs/exec-plans/active/2026-03-01-admin-crypto-migration-status.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "новая задача пиши новый план. в админ режим хочу коменда которая покажет сколкьо еще не перешло на новый секрет" and "ок и еще в хелп добавить ее чтоб я не искал"

## Change Plan

1. [x] Add `/crypto_migration_status` command in admin router.
2. [x] Include new command in `/help` output.
3. [x] Add router test that validates command output structure.
4. [x] Run targeted admin tests and `just check-fast`.

## Risks / Open Questions

- Keep query logic simple and deterministic for testability.
- Exclude `need_delete=1` wallets from totals to match migration script behavior.

## Verification

- `cd bot && uv run --package mmwb-bot pytest tests/routers/test_admin.py`
- `just check-fast`
