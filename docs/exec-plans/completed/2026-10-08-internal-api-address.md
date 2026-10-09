# internal-api-address: Internal API: username -> address

## Context

Внутренний read-only API для сервисов-партнёров: по Telegram-username вернуть
адрес кошелька пользователя бота. Один клиент, клиент на том же сервере.
Минимальная защита: статический токен в заголовке `X-Api-Token`, сравнение
`secrets.compare_digest`, бинд на `127.0.0.1` (уточнить, если клиент в docker).
Паттерн — существующий aiohttp-сервер из
`bot/infrastructure/services/notification_service.py:387-417`.
Контракт для клиента: `docs/api/internal-api.md`.

## Files/Directories To Change

- `bot/infrastructure/services/internal_api.py` (новый)
- `bot/other/config_reader.py`
- `bot/start.py`
- `bot/tests/infrastructure/test_internal_api.py` (новый)
- `bot/tests/infrastructure/test_notification_delivery_worker.py` (изоляция
  lifecycle-теста от локального `.env`: `internal_api_token → None`, чтобы
  тест не биндил реальный порт 8082)
- `docs/api/internal-api.md` (новый)
- `.env.template`
- `.env` (локально, в git не входит)
- `docs/exec-plans/active/2026-10-08-internal-api-address.md` (этот план)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User said (m00072): "ок давай так делать" — подтверждение состава работ из
> m00073 (файлы перечислены выше). Репо-правило: план создаётся перед первой
> правкой; пути соответствуют оговорённому составу.

## Change Plan

1. [x] `bot/other/config_reader.py`: `internal_api_port: int = 8082`,
       `internal_api_token: Optional[SecretStr] = None` (плюс
       `internal_api_host: str = "127.0.0.1"`).
2. [x] `bot/infrastructure/services/internal_api.py`: класс `InternalApi`
       (`start(host, port)`, `stop()`, `handle_address`); маршрут
       `GET /api/v1/address/{username}`; нормализация username
       `lstrip("@").lower()`; 401 без токена / неверный токен; 404 единый для
       «нет юзера» и «нет адреса»; 200 `{"username", "address"}`.
3. [x] `bot/start.py`: создать `InternalApi` и запустить синхронно
       `await internal_api.start(host, port)` в `on_startup` (запуск только
       если токен задан; ошибка бинда валит старт); объект кладётся в
       `dispatcher["internal_api"]`, остановка — явный
       `internal_api.stop()` в `on_shutdown_dispatcher` (паттерн
       NotificationService; graceful cleanup вместо отмены таска).
4. [x] `bot/tests/infrastructure/test_internal_api.py`: 200/401/404,
       нормализация `@Username` (пункт про 503 не нужен: без токена сервис не
       стартует, warning в лог — покрыто фактом запуска).
5. [x] `docs/api/internal-api.md`: контракт для клиента.
6. [x] `.env`: `INTERNAL_API_TOKEN` (`openssl rand -hex 32`),
       `INTERNAL_API_PORT=8082` (локально, git-ignored — проверено
       `git check-ignore .env`).
7. [x] Run `just check-fast` (+ целевой прогон нового теста): 490 passed,
       lint/arch/docs-линтеры зелёные; смоук хендлера 200/401/404 — OK.

## Risks / Open Questions

- Bind-адрес зависит от расположения клиента: тот же хост → `127.0.0.1`,
  клиент в docker-контейнере → `0.0.0.0`. По умолчанию `127.0.0.1`;
  уточняется при деплое, код параметризован.
- `user_name` в БД пишется lowercase без `@` (`common_start.py:650`);
  API ищет точное совпадение lowercase — исторических записей в другом
  регистре не обслуживаем (клиент получает 404).
- Владелец подтвердил fallback (m00617): пустой/битый `default_address` →
  публичный ключ дефолтного кошелька юзера (`MyMtlWalletBot`,
  `default_wallet==1`, `need_delete==0`, `id.desc()`) — как выплата в боте.
  Ни адреса, ни кошелька → 404.

## Verification

- `uv run pytest bot/tests/infrastructure/test_internal_api.py -q` — зелёный.
- `just check-fast` — зелёный.
- Смоук: поднять сервис на тестовом порту, `curl` без токена → 401,
  с токеном на известного юзера → 200 с адресом, на неизвестного → 404.
