# sep-assets-progress: Show /assets discovery progress with live message updates

## Context

`/assets` waits for anchor discovery (up to the 10 s total budget) without any
feedback, so the chat looks frozen and the user cannot tell whether the bot is
working or hung. The screen should show a live counter (`2 из 10`) that updates
roughly once per second while anchors are being checked.

## Files/Directories To Change

- `bot/infrastructure/services/anchor_discovery_service.py`
- `bot/routers/assets.py`
- `bot/langs/en.json`, `bot/langs/ru.json`
- `bot/tests/infrastructure/test_anchor_discovery_service.py`
- `bot/tests/routers/test_assets.py`
- `docs/exec-plans/active/2026-11-13-sep-assets-progress.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> все же долго висит /ассетс ... можем писать идет проверка/загрузка 2/60 и раз в секунду обновлять

## Change Plan

1. [x] Report completed-asset counts from `discover_assets` through an
   `on_progress` callback (per finished anchor, plus a periodic tick).
2. [x] Send an initial progress message and update it at most once per second
   via the tracked UI message, then replace it with the final list.
3. [x] Add localization keys and tests.
4. [x] Run `just check-fast` and `just check`.

## Risks / Open Questions

- Telegram edit limits: at most one edit per second per chat, no edit when the
  text did not change.
- Fast discovery (cached anchors) shows only the initial and final message.

## Outcome (2026-11-13)

- `discover_assets(..., on_progress=...)` reports `(checked_assets, total)` after
  every finished anchor and wakes up every 0.5 s, so a slow anchor still yields
  fresh ticks.
- `/assets` sends `⏳ Проверяю анкоры: 0 из N`, then rewrites that same tracked
  message at most once per second while discovery runs, and finally edits it into
  the anchor list with the keyboard (no extra messages in the chat).
- The progress message is skipped when the wallet has no issued assets.

## Verification

- `uv run --package mmwb-bot pytest tests/infrastructure/test_anchor_discovery_service.py tests/routers/test_assets.py` -> 43 passed
- `just check-fast`
- `just check`
