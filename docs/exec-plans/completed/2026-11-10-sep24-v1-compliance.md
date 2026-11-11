# sep24-v1-compliance: SEP-24 V1: spec compliance, SEP-10 token cache, challenge verification, localized texts

## Context

The hidden `/assets` SEP flow already discovers anchors (SEP-1 toml + `/info`),
performs SEP-10 and starts SEP-24 interactive deposit/withdraw. Live runs
against real anchors (`../sep_anchor/docs/runbooks/live-sep24-golden-client.md`,
`../sep_anchor/tools/live_client/golden_client.py`) proved the current bot code
is not spec-compliant and would fail in production:

- `POST .../interactive` is sent as form data with only `asset_code`; modern
  anchors require a JSON body `{asset_code, amount, account}` + Bearer JWT.
- The interactive transaction `id` is discarded, so nothing can ever be polled.
- SEP-10 challenge is signed without any verification.
- JWT is re-issued on every call (live anchors issue 10-minute tokens, so a
  cache keyed by token TTL is required), and 401 is not retried.
- Asset codes are case-sensitive (`yXLM`); discovery silently drops assets on
  a case mismatch.
- Status vocabulary in the wild includes the legacy
  `pending_user_transfer_start`; anchor errors are shown raw and in English.
- Payment instructions come in three shapes (modern
  `instructions.amount_in`, legacy `withdraw_anchor_account`, `more_info_url`
  page) and muxed M-destinations must never be decoded to G + id memo.

Scope: V1 "works per spec, verified against live anchors". No status polling
worker, no return channel, no automatic payments (those are V2/V3). Entry point
stays `/assets` only (option E1) for the trial period, plus a user-facing
disclaimer that anchors are third-party services.

## Files/Directories To Change

- `bot/core/models/anchor_asset.py`
- `bot/core/models/sep24.py` (new)
- `bot/infrastructure/services/anchor_discovery_service.py`
- `bot/infrastructure/services/sep24/__init__.py` (new)
- `bot/infrastructure/services/sep24/client.py` (new)
- `bot/infrastructure/services/sep24/challenge.py` (new)
- `bot/infrastructure/services/sep24/instructions.py` (new)
- `bot/infrastructure/services/sep24/token_store.py` (new)
- `bot/infrastructure/services/anchor_transaction_service.py`
- `bot/infrastructure/services/app_context.py`
- `bot/start.py`
- `bot/routers/assets.py`
- `bot/langs/en.json`, `bot/langs/ru.json`, `bot/langs/ua.json`,
  `bot/langs/am.json`, `bot/langs/hy.json`, `bot/langs/me.json`
- `bot/tests/infrastructure/test_anchor_transaction_service.py`
- `bot/tests/infrastructure/test_anchor_discovery_service.py`
- `bot/tests/infrastructure/test_sep24_challenge.py` (new)
- `bot/tests/infrastructure/test_sep24_instructions.py` (new)
- `bot/tests/infrastructure/test_sep24_client.py` (new)
- `bot/tests/infrastructure/test_sep10_token_store.py` (new)
- `bot/tests/routers/test_assets.py`
- `docs/exec-plans/active/2026-11-10-sep24-v1-compliance.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> да разрешаем

(earlier in the same session: "раскладка ок", "да добавляем", "как текст норм",
"а ну Е1 хватит чтоб обкатать")

## Change Plan

1. [x] Add `core/models/sep24.py` (challenge, token, interactive session,
   payment instructions, status vocabulary) and `signing_key` on
   `AnchorAssetSupport`.
2. [x] Add `sep24/instructions.py` with pure parsers for the three instruction
   shapes, muxed M-address pass-through and base64 hash-memo decoding.
3. [x] Add `sep24/challenge.py` with soft (C2) SEP-10 verification: home
   domain or web-auth host, server signature when `SIGNING_KEY` is published,
   hard failure only on account mismatch.
4. [x] Add `sep24/token_store.py` (Redis JWT cache, TTL from token expiry minus
   skew) and `sep24/client.py` (JSON interactive creation, transaction read,
   transaction list, challenge/token exchange).
5. [x] Rewire `anchor_transaction_service.py` as a thin facade over the new
   modules; keep the existing public methods used by the router.
6. [x] Parse `SIGNING_KEY` and resolve case-sensitive asset codes in
   `anchor_discovery_service.py`.
7. [x] Wire `app_context`/`start.py` so the facade gets the Redis-backed token
   store in production.
8. [x] Update `routers/assets.py`: default-wallet `account`, `lang`, stored
   `{id, type, url}`, localized texts, status/error mapping and the
   `sep_assets_disclaimer` text on `/assets` and on the interactive screen.
9. [x] Add localized keys to `bot/langs/en.json` and `bot/langs/ru.json`
   (other languages fall back to `en` by the existing rule) plus the
   disclaimer key in `ua`/`am`/`hy`/`me`.
10. [x] Add/update tests for every module and the router.
11. [x] Run `just check-fast` and move the plan to `completed/`.

## Risks / Open Questions

- C2 is deliberately soft: anchors whose challenge cannot be verified are still
  signed (warning + counter in logs), because live anchors deviate from the
  spec (Ultra serves `/auth` from a different host).
- JWT cache is best-effort: a flushed Redis just means one extra signature.
- `amount` is not collected in the bot UI in V1 (anchor form asks for it).
- Muxed M-destinations are surfaced verbatim; V1 does not pay them itself.

## Outcome (2026-11-10)

- SEP-24 `interactive` now posts a JSON body `{asset_code, account, [amount],
  [lang]}` with Bearer auth and keeps `{type, url, id}` in FSM state.
- SEP-10 tokens are cached in Redis per `user + public key + domain`, with the
  TTL taken from the token itself (minus 5 minutes); a 401 drops the cache entry
  and re-authenticates exactly once.
- Challenges are soft-verified (C2): account mismatch is a hard failure, other
  failures are counted in `SEP10_VERIFICATION_FAILURES` and logged, then the
  challenge is still signed.
- Discovery reads `SIGNING_KEY` and resolves the anchor's case-sensitive asset
  code spelling for protocol requests.
- All SEP flow texts go through `my_gettext`; anchor error codes and statuses
  are mapped, and the third-party disclaimer is shown on `/assets` and on the
  SEP-24 screen.
- Payment-instruction parsing (3 shapes, muxed pass-through, base64 hash memo,
  `more_info_url` scrape) is implemented and unit-tested, but the UI entry point
  for showing instructions/status needs a new button in
  `bot/keyboards/assets.py`, which is outside the approved paths: it moves to
  the V2 status slice (`GET /sep24/transaction` + polling worker).

## Verification

- `uv run --package mmwb-bot pytest tests/infrastructure/test_sep24_client.py tests/infrastructure/test_sep24_challenge.py tests/infrastructure/test_sep24_instructions.py tests/infrastructure/test_sep10_token_store.py tests/infrastructure/test_anchor_transaction_service.py tests/infrastructure/test_anchor_discovery_service.py tests/routers/test_assets.py`
- `just check` -> 1028 passed, 8 deselected; import boundaries,
  docs contract and exec-plan scope lock passed.
- `just check-fast` -> 634 passed.
