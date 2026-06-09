# clarify-swap-token-labels: Clarify swap token labels

## Context

Users are confused by the swap token selection screens because the first screen
said only "token for exchange" and did not clarify whether the selected token is
spent or received. The swap flow already uses the first selected token as
`send_asset_code` and the second selected token as `receive_asset_code`; only
localized UI labels need to change.

## Files/Directories To Change

- `bot/langs/am.json`
- `bot/langs/en.json`
- `bot/langs/hy.json`
- `bot/langs/me.json`
- `bot/langs/ru.json`
- `bot/langs/ua.json`
- `docs/exec-plans/active/2026-06-09-clarify-swap-token-labels.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> да давай, но это во всех языках поправь тогда
> ... тогда комить и пуш с переводом. остальное не трогаем

## Change Plan

1. [x] Update `choose_token_swap` in all supported language JSON files to say
       the user is choosing the token they spend/give.
2. [x] Update `choose_token_swap2` in all supported language JSON files to say
       the user is choosing the token they receive for the first token.
3. [x] Run localization JSON tests.
4. [x] Run secret scan before commit.

## Risks / Open Questions

- Translations for AM/HY/ME are best-effort and preserve the same placeholder
  contract as the existing strings.
- Notification amount behavior is intentionally not changed in this task.

## Verification

- `uv run pytest bot/tests/other/test_langs_json.py -q` passes.
- `just secret-scan` reports no leaks.
