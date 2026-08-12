# stellar-sealedbox: Stellar sealed-box file encryption

## Context

Users need interoperable encryption of text and files for Stellar addresses,
including decryption by server-held keys and by WebApp-held keys without
exposing plaintext or local secrets to the backend. The agreed design is in
`docs/plans/2026-08-12-stellar-sealedbox-design.md`; the implementation sequence
is in `docs/plans/2026-08-12-stellar-sealedbox-implementation.md`.

## Files/Directories To Change

- `bot/core/interfaces/services.py`
- `bot/infrastructure/services/`
- `bot/infrastructure/workers/`
- `bot/infrastructure/utils/telegram_utils.py`
- `bot/routers/mtltools.py`
- `bot/routers/sealedbox.py`
- `bot/keyboards/`
- `bot/middleware/notification_activity.py`
- `bot/langs/en.json`
- `bot/langs/ru.json`
- `bot/start.py`
- `bot/pyproject.toml`
- `bot/tests/`
- `shared/src/shared/`
- `webapp/app.py`
- `webapp/templates/`
- `webapp/static/js/`
- `webapp/static/css/`
- `webapp/static/vendor/`
- `uv.lock`
- `docs/plans/`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> `++`

## Change Plan

1. [x] Add and inject a focused Stellar sealed-box crypto/resource service.
2. [x] Add the localized MTL Tools FSM flow using the active wallet only.
3. [x] Add the encrypted Redis WebApp handoff and completion worker.
4. [x] Add local browser decryption with owner-checked ciphertext retrieval.
5. [x] Add unit, router, WebApp, worker, and regression coverage.
6. [x] Run the complete repository quality and secret-scan gates.

## Risks / Open Questions

- Raw sealed-box payloads carry no recipient or filename metadata; wrong-key
  failures and generic output naming are therefore intentionally unavoidable.
- WebApp plaintext must never cross the network boundary or enter Redis/logs.
- Telegram and Redis allocations must remain bounded around the 10 MiB limit.
- The in-memory abuse counter intentionally resets when the single bot process
  restarts.

## Verification

- Focused sealed-box, router, worker, WebApp, signing, and notification tests.
- `just fmt`, `just lint`, `just test`, `just arch-test`, `just secret-scan`.
- `git diff --check` and manual secret/plaintext/logging review.

Final results:

- Changed Python files were formatted; repository-wide `just fmt` was not used
  because unrelated legacy files have existing formatting drift.
- `just lint`: passed.
- `just test`: 730 passed, 7 deselected.
- `just arch-test`: passed.
- Deterministic end-to-end smoke suite: 120 passed.
- JavaScript syntax and `git diff --check`: passed.
- `just secret-scan` found two ignored local diagnostic logs under `localdoc/`;
  neither file is tracked or part of this change. A redacted scan of the full
  tracked and untracked change set found no leaks.
