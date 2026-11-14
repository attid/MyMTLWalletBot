# network-passphrase-config: Configurable network passphrase, mainnet default

## Context

The Stellar network passphrase is hardcoded as
`Network.PUBLIC_NETWORK_PASSPHRASE` in 26 places across the bot, including
`stellar_sign`, `async_stellar_send`, transaction builders and XDR renderers.
Any testnet run therefore signs with the mainnet hash and fails with
`tx_bad_auth`, so a bot-level testnet E2E (create wallet → send → order → swap)
is impossible today.

The passphrase becomes a setting with the **mainnet value as the default**, so
existing servers keep working without adding any config.

## Files/Directories To Change

- `shared/src/shared/constants.py`
- `bot/other/config_reader.py`
- `bot/other/stellar_tools.py`
- `bot/other/soroban_render.py`
- `bot/other/tx_render.py`
- `bot/infrastructure/services/stellar_service.py`
- `bot/core/use_cases/stellar/process_uri.py`
- `bot/infrastructure/factories/use_case_factory.py`
- `bot/start.py`
- `.env.template`
- `bot/tests/infrastructure/test_stellar_service.py`
- `bot/tests/other/test_stellar_tools.py`
- `bot/tests/core/test_process_uri_real.py`
- `docs/exec-plans/active/2026-11-14-network-passphrase-config.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ок давай но сделаем дефолт майннет. чтоб на сервере потом все заработало само без добавления конфигов

## Change Plan

1. [x] Add `DEFAULT_NETWORK_PASSPHRASE` (mainnet) to `shared.constants` and a
   `network_passphrase` setting defaulting to it.
2. [x] Make `StellarService` take `network_passphrase` (default mainnet) and use
   it in every builder/parser.
3. [x] Replace hardcoded passphrases in `stellar_tools`, `soroban_render`,
   `tx_render` with the setting.
4. [x] Pass the setting into `ProcessStellarUri` through the use-case factory
   (core must not import `other`).
5. [x] Document the optional env var in `.env.template`.
6. [x] Add tests proving a testnet passphrase flows into signing/building.
7. [x] Run `just check-fast` and `just check`.

## Risks / Open Questions

- Default stays mainnet, so an existing deployment needs no env change.
- A wrong `NETWORK_PASSPHRASE` makes signatures invalid; that is visible in the
  first transaction as `tx_bad_auth`.

## Outcome (2026-11-14)

- `shared.constants.DEFAULT_NETWORK_PASSPHRASE` (mainnet) and
  `TESTNET_NETWORK_PASSPHRASE` added; `Settings.network_passphrase` defaults to
  the mainnet value, so an existing server keeps working without new config.
- `StellarService` takes `network_passphrase` (default mainnet) and uses it for
  every builder/parser; `start.py` injects `config.network_passphrase`.
- `stellar_tools`, `soroban_render`, `tx_render` use `config.network_passphrase`.
- `ProcessStellarUri` receives the passphrase through `UseCaseFactory`
  (core does not import `other`); the factory defaults to mainnet.
- `.env.template` documents the optional `NETWORK_PASSPHRASE`.
- Tests: a testnet-built challenge keeps its passphrase through `ProcessStellarUri`;
  `stellar_sign` produces a signature valid for testnet and invalid for mainnet.

Note: `HORIZON_URLS` is a required setting (pre-existing, see
`adr/0004-horizon-failover.md`); local runs need it exported even though
`bot/.env` may not carry it.

## Verification

- `uv run --package mmwb-bot pytest tests/infrastructure/test_stellar_service.py tests/other/test_stellar_tools.py tests/core/test_process_uri_real.py`
- `just check-fast`
- `just check`
