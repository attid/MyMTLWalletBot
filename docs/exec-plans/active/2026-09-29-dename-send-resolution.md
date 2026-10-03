# dename-send-resolution: DeName recipient resolution

## Context

Implement the two P0 items in `../../../../docs/projects/mymtlwalletbot-dename-use-cases.md`: shared DeName read client with fail-closed resolution policy, and Send flow support for `<name>.<tld>`.

## Files/Directories To Change

- `bot/other/config_reader.py`
- `.env.template`
- `bot/infrastructure/services/app_context.py`
- `bot/infrastructure/services/dename_service.py` (new)
- `bot/start.py`
- `bot/routers/send.py`
- `bot/langs/*.json`
- `bot/tests/routers/test_send.py`
- `bot/tests/infrastructure/test_dename_service.py` (new)
- `bot/tests/other/test_config_dename.py` (new, if needed)
- `docs/architecture.md`
- `adr/` (only if the service boundary requires a decision record)
- `docs/exec-plans/active/2026-09-29-dename-send-resolution.md`
- `docs/exec-plans/completed/2026-09-29-dename-send-resolution.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence: User asked `выполни две задачи Р0` referring to the P0 rows in `docs/projects/mymtlwalletbot-dename-use-cases.md`, which explicitly identify `send.py`, configuration, an infrastructure service through `AppContext`, and tests as implementation areas. The workspace instructions authorize ordinary code, configuration, test and documentation edits for requested implementation.

## Change Plan

1. [x] Add a configured, validated DeName API client with bounded network behavior and explicit errors.
2. [x] Inject the client and resolve names in Send, rechecking before transaction creation and displaying full destination address.
3. [x] Add focused service and router tests, including legacy recipient regression cases.
4. [x] Document runtime configuration and resolution policy.
5. [ ] Run available lint, architecture and test gates; record limits.

## Risks / Open Questions

- The indexer is eventually consistent. A configured freshness limit and a second lookup reduce stale payments, but do not provide on-chain atomic resolution. The user must see the full address before signing.
- The bot uses Stellar public network; a DeName testnet API must never be used for payment resolution.

## Verification

- Focused DeName client and Send router tests.
- `just arch-test`, `just lint`, `just test-fast`, `git diff --check` when the local toolchain permits.

Static checks on 2026-09-29: Python AST for seven changed Python files, all six
localization JSON files, import-boundary check, and `git diff --check` passed.
The test and lint runtime is pending: this host has Python 3.12 but no `uv`,
`just`, `pytest`, `ruff`, or project packages. The user was asked to prepare the
workspace dependencies; no dependency installation was run by Codex.
