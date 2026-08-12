# Stellar Sealed-Box File Encryption Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task.

**Goal:** Add interoperable text and document encryption/decryption for Stellar wallets in MTL Tools, including local WebApp decryption for device-held keys.

**Architecture:** Keep sealed-box cryptography in a dedicated bot service, orchestration in a separate router, and browser-only secret handling in a dedicated WebApp screen. Use Redis only for the encrypted WebApp handoff and completion event; use an in-process limiter and semaphore for abuse/resource control.

**Tech Stack:** Python 3.12, aiogram 3, PyNaCl/libsodium, FastAPI, Redis, Telegram WebApp JavaScript, pytest, fakeredis.

---

### Task 1: Define sealed-box cryptography and resource controls

**Files:**
- Create: `bot/infrastructure/services/stellar_sealedbox_service.py`
- Create: `bot/tests/infrastructure/test_stellar_sealedbox_service.py`
- Modify: `bot/core/interfaces/services.py`
- Modify: `bot/infrastructure/services/app_context.py`
- Modify: `bot/start.py`
- Modify: `bot/pyproject.toml`
- Modify: `uv.lock`

1. Write failing unit tests for Stellar StrKey conversion, raw interoperability,
   raw-first/base64-second decryption, errors, overhead, size enforcement,
   rolling limits, and semaphore behavior.
2. Run the focused test and confirm RED.
3. Implement the focused service and inject one process-wide instance through
   `AppContext`.
4. Declare PyNaCl as a direct bot dependency and refresh the lockfile.
5. Run the focused test and confirm GREEN.

### Task 2: Add Telegram flow and navigation

**Files:**
- Create: `bot/routers/sealedbox.py`
- Create: `bot/tests/routers/test_sealedbox.py`
- Modify: `bot/routers/mtltools.py`
- Modify: `bot/start.py`
- Modify: `bot/middleware/notification_activity.py`
- Modify: `bot/infrastructure/utils/telegram_utils.py`
- Modify: `bot/langs/en.json`
- Modify: `bot/langs/ru.json`
- Modify: `bot/tests/routers/test_mtltools.py`
- Modify: `bot/tests/middleware/test_notification_activity.py`

1. Write failing `mock_telegram` tests for menu entry, manual/address-book
   recipient selection, text/document encryption, active-wallet decrypt,
   PIN/password continuation, unsupported media, limits, naming, Back, Home,
   and notification completion.
2. Run focused router tests and confirm RED.
3. Implement the FSM screens with shared `send_message()`, current-wallet-only
   behavior, bounded downloads, safe filenames, and terminal cleanup.
4. Add Russian and English copy; other languages use the existing English
   fallback.
5. Run focused router and localization tests and confirm GREEN.

### Task 3: Define encrypted WebApp handoff

**Files:**
- Modify: `shared/src/shared/constants.py`
- Modify: `shared/src/shared/schemas.py`
- Modify: `shared/src/shared/__init__.py`
- Modify: `bot/other/faststream_tools.py`
- Create: `bot/infrastructure/workers/sealedbox_worker.py`
- Modify: `bot/start.py`
- Create: `bot/tests/test_sealedbox_webapp_flow.py`

1. Write failing tests for random owner-bound tokens, one active request per
   user, 10-minute expiry, ciphertext-only storage, completion events, cleanup,
   FSM completion, and notification release.
2. Run the focused tests and confirm RED.
3. Add shared Redis fields/schema, bot publishing/cleanup helpers, and a
   completion worker registered with the existing broker.
4. Run the focused tests and confirm GREEN.

### Task 4: Add local browser decryption

**Files:**
- Modify: `webapp/app.py`
- Create: `webapp/templates/sealedbox.html`
- Create: `webapp/static/js/sealedbox.js`
- Add: `webapp/static/vendor/` sealed-box browser dependency
- Modify: `webapp/static/js/i18n.js`
- Modify: `webapp/static/css/style.css`
- Modify: `bot/keyboards/webapp.py`
- Create: `bot/tests/other/test_webapp_sealedbox.py`

1. Write failing backend/template/static tests for authenticated owner access,
   expired/foreign tokens, ciphertext download, local key selection, local
   decrypt/download, missing-key import, completion, and absence of plaintext
   uploads.
2. Run the focused tests and confirm RED.
3. Implement the owner-checked API and page, reusing `CryptoStorage` and a
   vendored browser sealed-box library.
4. Add the localized WebApp keyboard and user-facing strings.
5. Run focused WebApp tests and confirm GREEN.

### Task 5: Regression and completion

**Files:**
- Modify: `docs/exec-plans/active/2026-08-12-stellar-sealedbox.md`

1. Run all focused sealed-box, MTL Tools, signing, notification, language, and
   WebApp tests.
2. Run `just fmt`, `just lint`, `just test`, `just arch-test`,
   `just secret-scan`, and `git diff --check`.
3. Inspect the final diff for secret material, plaintext logging, direct router
   message sends, missing DB commits, and unrelated changes.
4. Mark the execution plan complete and move it with `just finish-task`.
