# 2026-03-10-sentry-error-handler: Sentry не получал ошибки из aiogram хендлеров

## Контекст

`sentry_sdk.init()` был настроен в `start.py`, но aiogram перехватывает исключения внутри
своего event loop и не пробрасывает их наружу — Sentry их не видел.
Решение взято из skynet_bot: использовать `dp.errors.register()` с aiogram's `ErrorEvent`.

## План изменений

1. [x] `bot/middleware/sentry_error_handler.py` — создать error handler по образцу skynet_bot,
   с поддержкой `callback_query.from_user` (в skynet только `message`)
2. [x] `bot/start.py` — добавить импорт и `dp.errors.register(sentry_error_handler)`
3. [x] `just check-fast` проходит

## Верификация

`just check-fast` — 347 тестов, все зелёные.
