# 2026-04-14-telegram-local-api-is-local: Enable is_local for custom Telegram Bot API

## Context

Local `telegram-bot-api` server returns absolute file paths (e.g.
`/var/lib/telegram-bot-api/<token>/photos/file_2.jpg`) from `getFile`.
Aiogram's default `TelegramAPIServer.from_base(...)` builds an HTTP URL by
concatenating that path to the base URL, producing a malformed URL and a
404 on `bot.download(...)`. Passing `is_local=True` makes aiogram read the
file directly from disk instead.

## Files/Directories To Change

- `bot/start.py`
- `docs/exec-plans/active/2026-04-14-2026-04-14-telegram-local-api-is-local.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> комить и пуш

## Change Plan

1. [x] Pass `is_local=True` to `TelegramAPIServer.from_base` in `bot/start.py`.

## Risks / Open Questions

- Bot container must share the `/var/lib/telegram-bot-api` volume with the
  `telegram_bot_api` service, otherwise aiogram will fail to open the file
  from disk. Tracked separately; not part of this change.

## Verification

- Send a photo to the bot in an environment with local Bot API server and
  confirm `bot.download(...)` succeeds instead of raising a 404.
