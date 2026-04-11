# telegram-api-url-startup-log: Log non-default telegram api url at startup

## Context

После добавления `TELEGRAM_API_URL` в `bot/start.py` нет диагностики: если
оператор указал self-hosted telegram-bot-api, он не увидит этого в логах и
при проблемах не сможет быстро понять, ушёл ли бот на кастомный сервер.
Нужно логировать URL при старте, но только если он задан — чтобы не шуметь
в дефолтном случае.

## Files/Directories To Change

- `bot/start.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] В `bot/start.py` в месте инициализации `AiohttpSession` добавить
       `logger.info(...)` с URL, если `config.telegram_api_url` задан.
2. [x] `just check-fast` проходит (356 tests).

## Risks / Open Questions

- Нет: изменение однострочное, не влияет на поведение когда URL не задан.

## Verification

- `just check-fast`
- Expected signal: гейт зелёный; при ручном запуске с установленной
  `TELEGRAM_API_URL` в логах видна строка с URL.
