# mtltools-xdr-sulguk-parse-mode: MMWB: fix <br> HTML in XDR preview (Sentry #3165)

## Context

GlitchTip issue 3165 / `MMWB-1RR` (plus `MMWB-1RQ` / #3125): pressing
`MTLToolsUpdateMulti` ends with
`TelegramBadRequest: can't parse entities: Unsupported start tag "br" at byte
offset 69`.

Diagnostic materials for this task (review round 2): `/inbox/report.md`,
`/inbox/repro.txt`, `/inbox/traceback.txt`. They confirm (a) the failing frame
is `bot/routers/mtltools.py:871` `await callback.message.answer(msg)`,
(b) `<br>` comes from `https://eurmtl.me/remote/decode` and is deliberately kept
by `_sanitize_decode_html`, (c) the bot default is `parse_mode="HTML"`
(`bot/start.py:322`) while sulguk's middleware only activates for
`SULGUK_PARSE_MODE`, and (d) byte offset 69 is the first `<br>` after the
sequence/balance prefix — exactly the reproduced 400.

Root cause:
`get_web_decoded_xdr()` (`bot/other/web_tools.py`) intentionally keeps `<br>` in
the sanitized HTML because the message is meant to be rendered by sulguk, but
`cmd_tools_update_multi` (`bot/routers/mtltools.py:871`) calls
`callback.message.answer(msg)` without `parse_mode`. The bot default is
`parse_mode="HTML"` (`bot/start.py`), sulguk's request middleware only handles
`parse_mode == SULGUK_PARSE_MODE` (`sulguk`), so the raw `<br>` reaches Telegram
and the update fails before `clear_last_message_id()` / `cmd_check_xdr()`, which
means no PIN/signing preview for the user.

Working reference call sites already pass the mode explicitly:
`bot/routers/sign.py:1302` and `bot/routers/wallet_setting.py:1619`.

### Sanitized evidence (self-contained, no PII)

The raw artifacts stay outside the repo (`/inbox/report.md`, `/inbox/repro.txt`,
`/inbox/traceback.txt`, sha256 `d8772d76…ad3726`, `903fb61c…8c3e75`,
`74b4b15c…d64082e`). Reviewers who cannot mount `/inbox` do not need them: the
relevant facts are reproduced below and by the regression test.

1. Container log (`mmwb_bot`, image `sha256:5c0fa754…6f4`), identical for both
events — failing application frame and Bot API answer:

   ```text
   File "/app/bot/routers/mtltools.py", line 871, in cmd_tools_update_multi
       await callback.message.answer(msg)
   ...
   aiogram.exceptions.TelegramBadRequest: Telegram server says - Bad Request:
   can't parse entities: Unsupported start tag "br" at byte offset 69
   ```

   Sentry events carry `callback_data='MTLToolsUpdateMulti'`; the earlier
   `MMWB-1RQ` (#3125) has the same frame with offset 68.
2. `get_web_decoded_xdr()` → `POST https://eurmtl.me/remote/decode` returns HTML
   with `<br>`; `_sanitize_decode_html()` keeps it on purpose (11 occurrences),
   reducing other tags to `<b>/<a>` (`bot/other/web_tools.py:21-22,49-52`).
3. Byte offset 69 is arithmetic, not a guess: the message prefix
   `Sequence Number … (свободно … XLM)` is 61 chars = 69 UTF-8 bytes, so the
   rejected tag is exactly the first `<br>` after the balance line.
4. No retry: `middleware/retry.py` re-raises `TelegramBadRequest` (400)
   immediately, so each button press produces one failed send.

Scope when reviewing: `bot/routers/mtltools.py:1-7,869-874` and
`bot/tests/routers/test_mtltools.py::test_cmd_tools_update_multi_renders_decoded_xdr_with_sulguk`.

## Files/Directories To Change

- `bot/routers/mtltools.py`
- `bot/tests/routers/test_mtltools.py`
- `docs/exec-plans/active/2026-10-26-mtltools-xdr-sulguk-parse-mode.md`
- `docs/exec-plans/completed/2026-10-26-mtltools-xdr-sulguk-parse-mode.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> Task d929aaa51e504febb11003df293f7978 orders: "Исправить минимально: явно
> передать parse_mode=SULGUK_PARSE_MODE в этом вызове, добавив импорт по
> существующему образцу bot/routers/sign.py и wallet_setting.py. Не менять
> глобальный parse_mode и санитайзер ... Добавить регрессионный тест для HTML с
> `<br>` (существующий bot/tests/routers/test_mtltools.py:420 мокает plain text)
> с проверкой parse_mode и корректной обработки без реального Telegram API ...
> Не выполнять git commit/push, deploy, рестарты, изменения продакшна или
> секретов." These three paths are the minimal source, test, and plan-bookkeeping
> scope for that order.

## Change Plan

1. [x] `bot/routers/mtltools.py`: import `SULGUK_PARSE_MODE` from `sulguk` (same
   shape as `bot/routers/sign.py`) and pass `parse_mode=SULGUK_PARSE_MODE` to the
   decoded-XDR `callback.message.answer(msg)` call; do not touch the global
   default, `_sanitize_decode_html`, or `web_tools`.
2. [x] `bot/tests/routers/test_mtltools.py`: add a regression test that mocks
   `get_web_decoded_xdr` with real sanitized decode HTML containing `<br>` (the
   mock Telegram server rejects `<br>` under `parse_mode="HTML"` exactly like the
   Bot API) and asserts the outgoing request uses `SULGUK_PARSE_MODE`, carries no
   `<br>` on the wire, and still reaches `cmd_check_xdr`.
3. [x] Run targeted tests (`tests/routers/test_mtltools.py`,
   `tests/other/test_web_tools.py`), then `just lint`, `just test-fast`,
   `just arch-test` / `just check-fast`.
4. [x] Docs: no user-facing contract change; no docs update needed beyond this
   plan.
5. [x] Plan bookkeeping: move this file to `docs/exec-plans/completed/` with
   `just finish-task` (no commit/push/deploy in this task).

## Risks / Open Questions

- sulguk raises `ValueError(f"Unsupported tag: {tag}")` on tags it cannot map;
  `_sanitize_decode_html` already reduces decode HTML to `<b>/<a>/<br>`, and
  `bot/tests/other/test_web_tools.py` covers that mapping, so the risk is low.
- Mock Telegram does not run sulguk's middleware, so the test registers
  `AiogramSulgukMiddleware` explicitly to prove the wire payload has no `<br>`;
  if that proves brittle, fall back to asserting `parse_mode` only.
- Out of scope without separate approval: the P2 items from the report (message
  length truncation in `mtltools.py`, `cmd_help`/`admin.py` HTML escaping).

## Verification

- New test fails before the fix with the mock-server 400
  `Unsupported start tag "br"` and passes after it (verified in rounds 1-3: RED
  with the `parse_mode` argument removed, GREEN with it restored).
- Round-3 review re-verification: 12 `test_mtltools.py` + 11 `test_web_tools.py`
  passed (23 targeted), `just test-fast` 573 passed, `just lint` and
  `just arch-test` passed. An earlier single `just lint` failure was a harness
  race (ruff read the file while the RED experiment rewrote it) and is not
  reproducible: serial re-run is green.
- `test_decoded_xdr_fixture_matches_sentry_br_offset` pins the fixture's first
  `<br>` to byte offset 69, the offset from Sentry MMWB-1RR, so the regression
  sample cannot silently drift from the incident.
- `ruff format --check` on both touched Python files: already formatted.
- No changes to `bot/start.py`, `bot/other/web_tools.py`, or production.
