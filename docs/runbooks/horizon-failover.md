# Horizon Failover Runbook

Бот сам переключается между нодами Horizon. Ручных команд нет — `/horizon` и
`/horizon_rw` удалены вместе с ADR-0004.

## Конфиг

```
HORIZON_URLS=https://horizon.stellar.org,https://horizon.stellar.lobstr.co
```

- Через запятую, **порядок = приоритет**, первая нода — primary.
- Суффикс `|ro` помечает read-only ноду: она используется для чтения и никогда
  для отправки транзакций.
- Переменная обязательная. Если её нет, контейнер падает на старте с
  `ValidationError` по `horizon_urls` — это ожидаемое поведение, а не баг.

Тюнинг (значения по умолчанию в `bot/other/config_reader.py`):

| Переменная | По умолчанию | Смысл |
| --- | --- | --- |
| `HORIZON_FAILOVER_BUDGET_SECONDS` | 25 | бюджет одного вызова на все попытки |
| `HORIZON_FAILOVER_MAX_ATTEMPTS` | 3 | попыток на вызов (по одной на ноду) |
| `HORIZON_REQUEST_TIMEOUT_SECONDS` | 8 | таймаут GET |
| `HORIZON_POST_TIMEOUT_SECONDS` | 15 | таймаут POST (submit) |
| `HORIZON_RATE_LIMIT_COOLDOWN_SECONDS` | 60 | база cooldown для 429 |
| `HORIZON_SERVER_ERROR_COOLDOWN_SECONDS` | 30 | база cooldown для 5xx/transport |
| `HORIZON_MAX_COOLDOWN_SECONDS` | 600 | потолок cooldown |
| `HORIZON_STICKY_SECONDS` | 60 | сколько держим выбранную ноду |
| `HORIZON_FREEZE_SWITCH_THRESHOLD` | 5 | переключений за окно до заморозки |
| `HORIZON_FREEZE_WINDOW_SECONDS` | 600 | окно подсчёта переключений |

## Что видит оператор

Алерт приходит в чат первого админа (`ADMIN_LIST[0]`):

- `⚠️ Horizon failover` — переключились: было → стало, причина, попытка.
- `🚨 Horizon: все ноды недоступны` — все ноды в cooldown, запросы не уходят.
- `🚨 Horizon freeze` — защита от флапа: переключений больше порога за окно.
- `✅ Horizon восстановлен` — вернулись на primary, N переключений за инцидент.

Доставка best-effort: если Telegram не принял сообщение, ошибка только
логируется. Правда о событии — всегда в логе.

## Логи

```
event=horizon_failover stage=attempt_failed pool=ro operation=load_account
url=https://horizon.stellar.org reason=rate_limited http_status=429 attempt=1
elapsed_ms=812 error=...
event=horizon_failover stage=attempt_succeeded pool=ro url=... attempts=2
event=horizon_failover stage=all_down pool=ro backoff_seconds=5
event=horizon_failover stage=freeze pool=ro switches=6
event=horizon_failover stage=budget_exhausted pool=ro operation=... attempts=2
event=horizon_failover stage=alert_failed pool=ro error=...
```

`stage=attempt_failed` пишется на каждую неудачу, включая те, что закончились
успехом на второй ноде. Stack trace на ожидаемых 429/5xx не пишется —
смотрите `reason` и `http_status`.

## Типовые ситуации

**429 на primary, всё работает.** Норма. Нода в cooldown на 60s, трафик на
второй ноде, админ получил один алерт. Ничего делать не нужно.

**`all_down` в 3 часа ночи.** Все ноды в cooldown: проверьте, что сеть/выход в
интернет жив (не только Horizon), и что лимиты провайдера не выбраны. Пока пул
пуст, запросы падают сразу, без похода в сеть, а окно backoff растёт
1→5→15→60s. Как только cooldown хотя бы одной ноды истекает, окно перестаёт
действовать и следующий запрос идёт на неё — рестарт не нужен.

**Нода отвечает 200, но данные неверные.** Failover это не ловит по
определению. Лечение: убрать ноду из `HORIZON_URLS`, рестарт контейнера. Другого
рычага нет — это осознанное решение (ADR-0004).

**`freeze` и алерты каждые несколько минут.** Значит ноды дёргают друг друга по
кругу. Смотрите лог: если это 429 на всех — увеличьте
`HORIZON_RATE_LIMIT_COOLDOWN_SECONDS`; если transport — проверяйте сеть.

**После деплоя контейнер не стартует.** Скорее всего в `.env` остались только
`HORIZON_URL`/`HORIZON_URL_RW`. Добавьте `HORIZON_URLS` и перезапустите.

## Деплой

1. Прописать `HORIZON_URLS` в окружении (серверный `.env` / swarm secret).
2. Только потом рестарт контейнера: без переменной он не поднимется.

## Проверка «пул жив» без прода

```
cd bot && HORIZON_URLS="https://a.example,https://b.example" \
  uv run pytest tests/infrastructure/test_horizon_pool.py \
                tests/other/test_horizon_failover_flow.py -q
```
