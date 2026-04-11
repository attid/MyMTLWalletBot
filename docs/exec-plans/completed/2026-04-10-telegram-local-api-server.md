# telegram-local-api-server: Add local telegram-bot-api server setting

## Context

Бот всегда ходит в публичный `api.telegram.org`. Нужна возможность указать
собственный сервер [tdlib/telegram-bot-api](https://github.com/tdlib/telegram-bot-api)
через env-переменную — это снимает ограничения публичного API (файлы до 2 ГБ,
меньше rate-limit, self-host вариант). Параметр должен быть опциональным:
если не задан — поведение не меняется, CI и существующие тесты не ломаются.

Aiogram уже поддерживает custom API через `TelegramAPIServer.from_base(url)` —
паттерн уже используется в `bot/tests/conftest.py` для мокирования.

## Files/Directories To Change

- `bot/other/config_reader.py`
- `bot/start.py`
- `.env.template`
- `bot/tests/other/test_config_telegram_api_url.py` (новый файл, регрессионный тест)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Добавить regression-тест `bot/tests/other/test_config_telegram_api_url.py`:
       проверяет, что `Settings().telegram_api_url` = `None` по умолчанию и
       читается из env-переменной `TELEGRAM_API_URL`.
2. [x] Добавить `telegram_api_url: Optional[str] = None` в `Settings` в
       `bot/other/config_reader.py` (рядом с `test_bot_token`).
3. [x] В `bot/start.py` импортировать `TelegramAPIServer` из
       `aiogram.client.telegram`, перед созданием `AiohttpSession` передавать
       `api=TelegramAPIServer.from_base(config.telegram_api_url)` при наличии
       настройки. Оба ветвления (`test_mode`/production) используют общий
       `session` — менять сами ветки не нужно.
4. [x] Добавить `TELEGRAM_API_URL=` в секцию `# === Bot Identity ===` файла
       `.env.template` с комментарием-описанием.
5. [x] Пропустить обновление `docs/` — изменение внутреннее, не меняет публичные
       контракты и покрыто regression-тестом.
6. [x] `just check-fast` проходит локально (356 tests passed).

## Risks / Open Questions

- Если пользователь укажет URL без схемы/с некорректным форматом —
  `TelegramAPIServer.from_base` может упасть только при первом запросе к API.
  Это ok: параметр опциональный, ошибка будет видна сразу при старте бота.
- `test_import_sanity.py` не должен начать падать из-за нового импорта
  `TelegramAPIServer` — он уже импортируется в `bot/tests/conftest.py`.

## Verification

- `uv run pytest bot/tests/other/test_config_telegram_api_url.py -q`
- `uv run pytest bot/tests/other/test_import_sanity.py -q`
- `just check-fast`
- Expected signal: новый regression-тест зелёный, import-sanity не деградирует,
  полный быстрый гейт зелёный.
