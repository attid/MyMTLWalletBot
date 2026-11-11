# sep24-review-fixes: SEP-24 review round 1: hard challenge invariants, WebApp token cache, status gating

## Context

External `agy` review of the SEP-24 V1/V2a diff
(`docs/drafts/agy_sep24_v1_v2a_round1_review.md`) found three P1 defects after
manual verification:

1. `verify_sep10_challenge` only rejects an account mismatch when the challenge
   account could be parsed. With an unparsable challenge, a non-`ManageData`
   first operation, or an operation without a source, `client_account` is
   `None`, so the service logs "signing anyway" and signs arbitrary XDR with the
   user's key (which then goes back to the anchor, who can submit it).
2. WebApp wallets (`use_pin == 10`) never store their SEP-10 token, so the new
   status screen always answers "authorize again" — an endless loop.
3. Payment instructions are rendered for terminal statuses (`completed`,
   `refunded`, `expired`), inviting a second payment on a closed transaction.

Plus P2/P3 findings: `sep24_status_error` key collision (status `error` renders
the fetch-error template), unguarded challenge fetch (spinner hangs on 5xx),
anchor error text discarded, `?` duplication for endpoints with query params,
native-XLM trustline false positive, double space for unknown amounts, weak
`is_muxed`, dead `domain_candidates`, unused `extract_destination_from_html`,
and a wrong 64-byte branch in `decode_hash_memo`.

## Files/Directories To Change

- `bot/core/models/sep24.py`
- `bot/infrastructure/services/sep24/challenge.py`
- `bot/infrastructure/services/sep24/client.py`
- `bot/infrastructure/services/sep24/instructions.py`
- `bot/infrastructure/services/sep24/__init__.py`
- `bot/infrastructure/services/anchor_transaction_service.py`
- `bot/routers/assets.py`
- `bot/keyboards/assets.py`
- `bot/langs/en.json`, `bot/langs/ru.json`
- `bot/tests/infrastructure/test_sep24_challenge.py`
- `bot/tests/infrastructure/test_sep24_client.py`
- `bot/tests/infrastructure/test_sep24_instructions.py`
- `bot/tests/infrastructure/test_sep24_view.py`
- `bot/tests/infrastructure/test_anchor_transaction_service.py`
- `bot/tests/routers/test_assets.py`
- `docs/drafts/`
- `docs/exec-plans/active/2026-11-10-sep24-review-fixes.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> да исправляй

(previously confirmed path list in the same session)

## Change Plan

1. [x] Make challenge invariants strict: parse failure, `sequence != 0`,
   non-`ManageData` first operation or missing operation source is a hard
   rejection (new `Sep10ChallengeInvalid`, common base `Sep10ChallengeRejected`).
2. [x] Cache the SEP-10 token on the WebApp path (`remember_sep10_token`).
3. [x] Render payment instructions only for the statuses that actually wait for
   the user's transfer.
4. [x] Fix the `sep24_status_error` key collision and render unknown anchor
   error text instead of the generic message.
5. [x] Guard challenge fetching in both SEP-10 handlers so callback spinners
   always resolve.
6. [x] Merge query parameters safely in the HTTP transport.
7. [x] P3 cleanups: native-XLM trustline guard, no refresh without a stored id,
   amount-less payment wording, regex-based muxed detection.
8. [x] Remove dead code (`domain_candidates`, `extract_destination_from_html`)
   and fix the 64-byte hash-memo branch.
9. [x] Add/update tests for all of the above.
10. [x] Run `just check-fast` and `just check`; second review round.

## Risks / Open Questions

- Strict rejection of unusual challenges may refuse anchors that were previously
  signed blindly; that is the intended trade-off (C2 tolerates domain/timebound
  deviations only, not structural ones).
- WebApp token durable caching uses the same Redis store as the PIN path.

## Outcome (2026-11-10)

Round 1 findings (`docs/drafts/agy_sep24_v1_v2a_round1_review.md`) are fixed:

- challenge invariants are strict (parse failure, `sequence != 0`, non
  `ManageData` first op, missing op source, account mismatch) and the facade
  raises `Sep10ChallengeRejected` without signing — regression test proves a
  payment XDR is never signed and never POSTed;
- WebApp-issued SEP-10 tokens are cached (`remember_sep10_token`), so the status
  screen works for `use_pin == 10`;
- instructions are rendered only while the anchor awaits the user's transfer;
- `sep24_status_error` split into `sep24_status_failed` (status) and
  `sep24_status_fetch_error` (read failure);
- challenge fetches are guarded, unknown anchor error text is shown escaped,
  query params merge safely, native XLM needs no trustline, refresh button is
  optional, amount-less payment wording added, `is_muxed_address` lives in core;
- dead code removed (`domain_candidates`, `extract_destination_from_html`),
  `decode_hash_memo` accepts only 32-byte hashes.

Round 2 (`docs/drafts/agy_sep24_v1_v2a_round2_review.md`) reported **no P1** and
no regressions, so per the review skill the remaining P2/P3 findings stay in the
backlog instead of this diff: 401 swallowed in the history request, missing
return keyboard on error screens, raw `str(exc)` on the status screen,
`native` asset ref falling back to the default asset, the `am -> hy` language
alias, the trustline warning on terminal statuses, unescaped asset code/domain
in the support formatter, non-dict JWT claims, and three small cleanups
(unused `sep24_error_i18n_key`, `is_muxed_destination` wrapper, thin
`fetch_transactions_with_token` delegation).

## Verification

- `uv run --package mmwb-bot pytest tests/infrastructure tests/routers/test_assets.py`
- `just check-fast` -> 646 passed (after round-1 fixes).
- `just check` -> green; import boundaries, docs contract, scope lock passed.
