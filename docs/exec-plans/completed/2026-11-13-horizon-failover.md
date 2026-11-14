# horizon-failover: Automatic horizon failover pool (3 nodes, admin alerts, /horizon removed)

## Context

Сейчас горизонт переключается **вручную** командами `/horizon` и `/horizon_rw`
(`bot/routers/admin.py:494-518`), и это переключение **не работает**: URL
фиксируется в `StellarService` на старте (`bot/start.py:401`) и в
`AnchorDiscoveryService` на импорте роутера (`bot/routers/assets.py:54` →
`anchor_discovery_service.py:79`). В итоге часть трафика (`stellar_tools`,
читающий `config.horizon_url` per-call) идёт на новую ноду, а часть
(`app_context.stellar_service`, все use-cases, anchor discovery) — на старую.
Два горизонта в одном процессе = расхождение по sequence/офферам.

Дополнительный факт: 2026-09-05 `https://horizon.stellar.org` отдавал 429,
`stellar-notifier` в Swarm уходил в restart-loop по healthcheck.

Требуется: автоматический failover по пулу нод с алертом админу; ручные
команды удаляются, а не чинятся.

Все числа и семантика ниже прошли прожарку (grilling) с владельцем — это
согласованный контракт, менять его без нового согласования нельзя.

## Решения (согласованы, не пересматривать)

### Триггер

- Failover **только** на: transport/timeout (`stellar_sdk.exceptions.ConnectionError`,
  `asyncio.TimeoutError`), HTTP `>= 500`, HTTP `429`.
- **429** приходит как `BadRequestError` (см. `stellar_sdk.exceptions.raise_request_exception`),
  поэтому классификация строго по `.status == 429`, а не по типу исключения.
- Бизнес-ошибки (400/404: `tx_bad_seq`, `op_underfunded`, account not found)
  failover **не** вызывают и алертов не порождают — уходят наверх как сейчас.
- Детект лага ledger (нода отвечает 200, но отстаёт) — **вне скоупа**.
- `Retry-After` недоступен (Response не сохраняется в `BaseRequestError`) →
  собственные cooldown'ы.

### Пул и конфиг

- Источник нод — **только конфиг**: `HORIZON_URLS` (список через запятую,
  порядок = приоритет, первая = primary). Переменной нет → **падаем на старте**
  (обязательное поле pydantic, отдельный код не нужен).
- Хардкод-адресов не остаётся: `horizont_urls`, `horizon_url`, `horizon_url_rw`
  удаляются из `bot/other/config_reader.py`.
- RO (`horizon_url`) и RW (`horizon_url_rw` / submit) — **один список
  кандидатов, разные текущие индексы**: RO может уехать на ноду, которая не
  принимает `POST /transactions`, RW — нет. Нода, не принимающая submit,
  помечается и RW-пулом пропускается.
- Состояние пула — **только в памяти процесса**. Рестарт = всё забыли, старт
  с primary.

### Поведение вызова

- Каждая нода пробуется **один раз**, максимум 3 захода (по числу нод),
  общий бюджет `HORIZON_FAILOVER_BUDGET_SECONDS = 25`.
- Клиент создаётся с `request_timeout=8`, `post_timeout=15` (иначе 3×11s не
  влезают в бюджет).
- Повтор выполняется на следующей живой ноде в том же вызове; бюджет
  исчерпан → ошибка наверх без «досиживания».
- 429 на одной ноде → нода в cooldown, идём на следующую. Если 429 дали все
  ноды → общий backoff 1→5→15s (потолок 60s), затем ошибка. По кругу без
  паузы не долбим.
- `async_stellar_send` (submit) ретраится по тем же правилам (конверт
  подписан, Horizon идемпотентен по хешу). `tx_duplicate` остаётся обычной
  ошибкой — поведение не ухудшаем и не улучшаем.

### Cooldown'ы и анти-флап

- 429 → база 60s; 5xx/transport → база 30s; ×2 за каждый подряд отказ той же
  ноды; потолок 600s; полный сброс при успехе. Все числа — в конфиг.
- Sticky 60s: после переключения целевая нода не меняется 60s.
- Freeze: `>5` переключений за 10 минут → заморозка на текущей ноде до конца
  окна.
- Возврат на primary — **ленивый**: истёк cooldown primary → следующий вызов
  снова пробует primary первым. Фонового health-probe джоба **нет**.

### Алерты

- Три события: `switch` (было → стало, причина, счётчик), `all_down/freeze`
  (критично), `recovery` (вернулись на primary, N переключений за инцидент).
- Адресат — `config.admins[0]` (как «Bot started/stopped»).
- Канал — прямой `bot.send_message` с `suppress`, best-effort, **без** очереди,
  ретраев и Redis-доставки. Дедуп — на инцидент.
- Аварийного выключателя ноды (`HORIZON_EXCLUDE_URLS`) **нет** — сознательное
  решение: единственный ручной рычаг — правка конфига + рестарт.

### Наблюдаемость

- Логи не экономим: warning на каждую неудачную попытку и на переключение
  (с `detail`/`title` от Horizon), error на all-down/freeze, info на recovery.
- Structured: `logger.bind(event="horizon_failover", role="ro|rw", from_url,
  to_url, reason="rate_limited|server_error|unreachable", http_status, attempt,
  elapsed_ms)`.
- Stack trace на ожидаемых 429/5xx — **не** пишем.

### Границы

- Покрываются **все** call-site'ы. Точный подсчёт (проверено grep'ом):
  `bot/other/stellar_tools.py` — **18** `ServerAsync(...)` (17 RO с
  `config.horizon_url` + 1 RW с `config.horizon_url_rw` в `async_stellar_send`),
  плюс **1** дополнительная точка — `StellarService(config.horizon_url)` внутри
  `stellar_get_balance_str` (`stellar_tools.py:758`); итого 19 мест.
  `bot/infrastructure/services/stellar_service.py` — **12** `ServerAsync(...)`.
  Полу-покрытие запрещено — это ровно текущий баг.
- Конструкторы `StellarService`/`AnchorDiscoveryService` **сохраняют параметр
  `horizon_url=` как явный пин** (используется только тестами): без аргумента
  URL резолвится из пула на каждый вызов, с аргументом — берётся переданный.
  Поэтому 13 тестов `test_anchor_discovery_service.py` и явные
  `StellarService(horizon_url=...)` в роутерных тестах **не переписываются**.
  Guard-тест ловит именно заморозку дефолта (`self._horizon_url = ` с
  `config.`/пула), а не explicit-pin в отдельном поле.
- `AnchorDiscoveryService`: URL резолвится **на каждый запрос** (актуальный на
  его минуту), **без** собственного failover-цикла (ошибка → ошибка), TTL кеша
  anchor-данных остаётся **1 час**, собственный retry (`FETCH_ATTEMPTS = 2`)
  не трогаем.
- `stellar-notifier` (другой репозиторий, своя `HORIZON`) и `webapp`
  (обращений к Horizon нет) — **вне скоупа**.
- `/horizon` и `/horizon_rw` **удаляются**, не чинятся.

## Files/Directories To Change

Новое:

- `bot/infrastructure/services/horizon_pool.py` — состояние пула, классификатор
  ошибок, `with_horizon_failover`, module-level синглтон `get_horizon_pool(role)`
  + `setup_horizon_pool(...)` (паттерн как у `setup_async_utils` в
  `bot/infrastructure/utils/async_utils.py`).
- `bot/infrastructure/services/horizon_alerts.py` — сообщения админу
  (`config.admins[0]`), дедуп на инцидент.
- `bot/tests/infrastructure/test_horizon_pool.py` — unit: ротация 3 нод,
  cooldown + экспонента + потолок, sticky, freeze, ленивый возврат на primary,
  пул из одной ноды, «все 429 → backoff».
- `bot/tests/infrastructure/test_horizon_error_classification.py` — unit:
  429/5xx/transport → failover; 400/404 → не failover.
- `bot/tests/other/test_horizon_failover_flow.py` — интеграция на трёх
  фейк-горизонтах: 429/500/refused → успех на второй ноде, ровно одно
  сообщение админу.
- `bot/tests/other/test_no_sticky_horizon_url.py` — guard-тест (ast/regex):
  падать, если `horizon_url=config.` или `self._horizon_url =` встречается в
  `__init__` или модульном скоупе `bot/infrastructure/services/*` и
  `bot/other/stellar_tools.py`.
- `adr/0004-horizon-failover.md` — решение: пул с cooldown, без ручного
  переключения, состояние в памяти.
- `docs/runbooks/horizon-failover.md` — что видит оператор в логах/алертах,
  что делать при «все ноды down», порядок деплоя.

Правка:

- `bot/other/config_reader.py` — обязательный `horizon_urls: list[str]`,
  настройки cooldown/sticky/budget/attempts; удалить `horizon_url`,
  `horizon_url_rw`, `horizont_urls`.
- `bot/other/stellar_tools.py` — все 20 `ServerAsync(...)` через пул.
- `bot/infrastructure/services/stellar_service.py` — 12 call-site + URL
  резолвится на каждый вызов (`url_provider`), параметр `horizon_url=`
  остаётся для явной фиксации в тестах.
- `bot/infrastructure/services/anchor_discovery_service.py` — URL на каждый
  запрос; TTL 1 час без изменений.
- `bot/routers/admin.py` — удалить `cmd_horizon`/`cmd_horizon_rw`, импорт
  `horizont_urls`, строку `/horizon | /horizon_rw` в help.
- `bot/start.py` — `setup_horizon_pool(...)`, `StellarService` с провайдером,
  убрать регистрацию команд `/horizon`, `/horizon_rw` из меню и help.
- `docker-compose.yml` — `HORIZON_URL`/`HORIZON_URL_RW` → `HORIZON_URLS`.
- `.env.template` — то же.
- `docs/architecture.md` — короткая секция про пул.
- `docs/runbooks/README.md` — ссылка на новый runbook.
- Тесты (все файлы, где живёт `config.horizon_url`; проверено grep'ом):
  - `bot/tests/conftest.py` — `mock_horizon` (6 ссылок на `config.horizon_url`)
    → `config.horizon_urls = [url]` + сброс состояния пула между тестами;
    новый helper для тестов вида `patch_horizon(url)` взамен `patch(...)`.
  - `bot/tests/routers/test_swap.py` — **9** `patch("other.config_reader.config.horizon_url", ...)`.
  - `bot/tests/routers/test_mtltools.py` — **1** `patch("other.stellar_tools.config.horizon_url", ...)`.
  - `bot/tests/routers/test_admin.py` — удалить `test_cmd_horizon_cycle` и
    убрать `config.horizon_url` из фикстуры/teardown.
  - `bot/tests/other/test_startup_wiring.py` — меню команд.
  - `bot/tests/other/test_config_telegram_api_url.py` — env-фикстура.
  - `bot/tests/infrastructure/test_anchor_discovery_service.py` — **не меняется**
    (явный `horizon_url=` остаётся валидным пином, см. решение выше).

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> «да, создавай план-файл» — после согласования итогового плана v2 (список
> файлов выше) в прожарке. Разрешение относится к созданию этого план-файла;
> правки кода начинаются только по отдельному «начинай».

## Change Plan

1. [x] `bot/other/config_reader.py`: `HORIZON_URLS` → `horizon_urls: list[str]`
   (обязательное), конфиг cooldown/sticky/budget/attempts; удалить
   `horizon_url`, `horizon_url_rw`, `horizont_urls`; обновить
   `docker-compose.yml` и `.env.template`.
2. [x] `bot/infrastructure/services/horizon_pool.py`: классификатор ошибок,
   состояние пула (cooldown ×2 / потолок 600s / sticky 60s / freeze 5 за
   10 min / ленивый возврат / backoff при «все 429»), `with_horizon_failover`
   (1 заход на ноду, максимум 3, бюджет 25s, `request_timeout=8`,
   `post_timeout=15`), синглтон + `setup_horizon_pool`, structured-логи.
3. [x] `bot/infrastructure/services/horizon_alerts.py` + wiring в `start.py`:
   `switch`/`all_down`/`recovery` на `config.admins[0]`, дедуп на инцидент,
   best-effort `bot.send_message`.
4. [x] Разморозить URL: `StellarService` (`url_provider`, 12 call-site) и
   `AnchorDiscoveryService` (URL на каждый запрос, TTL 1 час) — без этого шага
   пул декоративен.
5. [x] `bot/other/stellar_tools.py`: 18 `ServerAsync(...)` (17 RO + 1 RW
   submit) + `StellarService(config.horizon_url)` в `stellar_get_balance_str`
   → через пул (без аргумента, провайдер по умолчанию); submit ретраится по
   тем же правилам. Пересчитать оккуренсы после правки: `grep -c "ServerAsync("
   должен остаться 18, `config.horizon_url` — 0.
6. [x] Удалить `/horizon` и `/horizon_rw`: `bot/routers/admin.py`,
   `bot/start.py` (регистрация команд + help).
7. [x] Тесты: unit пула и классификатора, интеграция на трёх фейк-горизонтах,
   регресс «URL не прилип» для `StellarService`/`AnchorDiscoveryService`,
   guard-тест против заморозки URL, правка существующих тестов и `conftest.py`
   (`test_swap.py`, `test_mtltools.py`, `test_admin.py`,
   `test_startup_wiring.py`, `test_config_telegram_api_url.py`).
8. [x] Доки: `adr/0004-horizon-failover.md`,
   `docs/runbooks/horizon-failover.md`, `docs/runbooks/README.md`,
   `docs/architecture.md`.
9. [x] `just fmt && just lint && just arch-test && just test-fast && just test`.
10. [x] `.github/workflows/{ci,e2e-nightly,external-integration}.yml`:
    `HORIZON_URL`/`HORIZON_URL_RW` → `HORIZON_URLS` (иначе CI падает на
    импорте конфига). Разрешено владельцем отдельно от исходного списка.

## Risks / Open Questions

- `request_timeout=8` может отбросить «медленную, но живую» ноду. Принято
  сознательно: 8s для `/accounts` и `/fee_stats` — уже проблема ноды.
- Худшее ожидание пользователя при мёртвых нодах — ~25s (бюджет), затем ошибка.
- Состояние в памяти: после рестарта снова начинаем с primary (принято).
- Ручного escape hatch нет: единственный рычаг — конфиг + рестарт (принято).
- 400/404 никогда не триггерят failover — если Horizon начнёт отдавать 429 в
  виде 400 с другим кодом, классификатор его не увидит (проверяется тестом).
- Деплой: серверный `.env` со старыми `HORIZON_URL*` и без `HORIZON_URLS` =
  контейнер не стартует. Правка серверного `.env` — действие владельца, не в
  рамках плана.
- Push — действие владельца, вне плана.

## Verification

- `just test-fast` — unit пула/классификатора/guard зелёные.
- `just test` — интеграционный flow «429 → успех на второй ноде → одно
  сообщение админу» зелёный; тесты удалённых команд отсутствуют.
- `just arch-test` — план-скоуп и границы импортов не нарушены.
- Ручная проверка в логах на стенде: одна строка `event=horizon_failover` на
  попытку и на переключение, админу приходит одно сообщение.
- Сигнал «пул работает»: при мёртвой первой ноде вызов succeeds на второй,
  `api_settings`/балансы грузятся; при всех мёртвых — ошибка и ровно один
  critical-алерт.
