# notification-flood-hardening: разнос отправок по времени, бандл по транзакции, фильтр по трейдам

## Context

Инцидент 2026-10-30 (docker3): контрагент `GBTEZE3J…2NUA2EKV` пылевыми объёмами
исполнял ордера делегата `GCVVMTQY…Y5F4H` на EURMTL/USDC — 3 246 сделок за 9 часов,
до 93 исполнений в одной транзакции. Каждое исполнение стало отдельным сообщением,
273 сообщения ушли в чат 262632819 за 4 минуты, Telegram включил per-chat flood-limit
(первый 429 в 04:21:41, окна 279 s → 1599 s → 2430 s), доставка встала на часы.

Подтверждено данными (Redis `notification:dedupe:262632819`, Firebird
`NOTIFICATION_FILTERS`):

- 8 743 события за окно дедупа, из них 7 990 trade (91%), 2 773 транзакции,
  max 93 события на транзакцию, 152 tx с ≥20 событиями;
- очередь и локи после инцидента пусты: ничего не потеряно, доставка «опоздала»,
  а не «упала»;
- фильтров 5 339 на 5 189 пользователей, из них 5 313 — `payment`; трейдовых 21.
  У пострадавшего единственный фильтр — `payment/XLM/0.10`, трейдового нет.

Что этим планом исправляется:

1. Единственный регулятор исходящей скорости — спящий inline ретрай в
   `bot/middleware/retry.py`, который (а) держит per-user lock, (б) обрывается
   `asyncio.timeout(30)` и потому теряет `retry_after`, (в) не помнит, что чат
   заглушён — из-за чего окно только эскалирует.
2. Нет склейки: одна транзакция = до 93 отдельных сообщений.
3. Фильтр по трейдам невозможно создать из UI (единственная точка входа —
   `create_filter_from:` по записи истории; история — 50 записей, 12 ч, в памяти).

Связанные документы: `adr/0001-delayed-blockchain-notification-delivery.md`
(durability/ordering работают — их не меняем), `adr/0002-worker-owned-notification-flow-completion.md`.

### Ключевые решения (подтверждены пользователем)

1. **Владелец скорости один — координатор.** Темп: не чаще одного сообщения в секунду
   на чат (настраиваемо). `chat_cooldown_until = now + retry_after`
   в Redis; все отправки в этот чат, включая `edit_message_reply_markup` (badge ест
   тот же лимит), паркуются до срока. `RetryRequestMiddleware` перестаёт спать и
   поднимает типизированную ошибку; ожидание — не в middleware.
2. **Таймаут один.** Убираем конкуренцию `delivery_timeout=30` и сна ретрая:
   решение «ждать или припарковать чат» принимает координатор.
3. **Бандл — по транзакции, внутри `process_notification`.** Все трейды одной tx
   приходят в одном payload (`payload.operation.trades`) → группировка без таймеров
   и без состояния между запросами. Окно в воркере отклонено как лишняя сущность.
4. **Порядок: фильтр → бандл → бюджет размера.** Бандл собирается только из
   прошедших фильтр событий.
5. **Переполнение — шапка + первые X операций + «…и ещё N»**, ссылка ведёт на
   `https://viewer.eurmtl.me/transaction/{hash}` (пользователь подтвердил, что путь
   работает). Построчные `viewer`-ссылки в бандле не нужны → строка короче,
   X = 15.
6. **Длину одиночной операции не меряем**: одна операция ~150 видимых символов,
   до лимита 4096 не достаёт. Бюджет размера считается один раз на бандл, по
   видимым символам (без HTML-тегов): вырезание тегов + `html.unescape`.
7. **Hold не трогаем.** `notification_hold_seconds` (скользящее окно активности,
   ADR-0001) — отдельный механизм, в стеке таймаутов не участвует. Учитываем его
   побочку: hold накапливает очередь и выпускает залпом, поэтому ограничение частоты нужно
   независимо.
8. **Фильтр по трейдам** — не «починить матчинг» (он работает), а добавить точку
   входа в настройках с префиллом суммы из последней сделки.
9. **Бандл — только для трейдов** (maker fills). `payment`, `claim_claimable_balance`,
   `manage_*_offer`, `change_trust` и прочее идут по одному сообщению, как сейчас:
   у них нет источника пачки в одном payload. Трейды — 7 990 из 8 743 событий (91%).
10. **Ничего не дропаем.** Переполнение решается задержкой, не потерей: пылевые
    бандлы ждут в очереди и уходят после снятия парковки. Компенсирующий контроль
    вместо drop-политики — алерт по глубине очереди и возрасту головы.
11. **Семантика фильтра по активу у мейкера.** Сделка описывает две стороны:
    проданное (`sold`) и купленное (`bought`). Сейчас фильтр сравнивает только
    купленную сторону (`display_asset_code` = `trade_bought_asset`), поэтому фильтр
    «EURMTL ≥ 0.1» у мейкера, продающего EURMTL за USDC, не срабатывает никогда.
    Меняем: фильтр срабатывает, если совпал **любой** из двух активов, и сумма
    берётся с той стороны, где актив совпал.

## Files/Directories To Change

Бот — доставка и скорость:
- `bot/middleware/retry.py` — убрать inline `asyncio.sleep(retry_after)` для
  `SendMessage`/правок разметки; поднимать типизированную ошибку
  `ChatCooldownRequired(retry_after, chat_id)`.
- `bot/infrastructure/services/notification_coordinator.py` — проверка cooldown
  перед каждой отправкой, парковка чата, снятие парковки, лог/метрика
  `notification_chat_parked`; согласование `delivery_timeout` с новым потоком.
- `bot/infrastructure/services/notification_redis_store.py` — ключ
  `notification:cooldown:{user_id}`, атомарные скрипты park/unpark, ключ темпа отправки
  (минимальный интервал между отправками в один чат), методы в `NotificationStore`.

Бот — бандлинг:
- `bot/infrastructure/services/notification_service.py` — в maker-ветке
  `process_notification` (цикл `for i, trade in enumerate(trades)`) собирать один
  бандл на `(user_id, tx_hash)`; `notification_id` бандла стабилен
  (`{tx}:trade_bundle:0:{user_id}`), в `data` добавляется `bundle`
  (список строк + счётчик + hash) без изменения класса `BlockchainNotification`.
- `bot/infrastructure/utils/notification_utils.py` — рендер бандла: шапка со
  ссылкой на транзакцию, первые X строк, «…и ещё N»; helper расчёта видимой длины.
- `bot/other/config_reader.py` — параметры: `notification_bundle_max_lines`,
  `notification_chat_min_interval_seconds`, `notification_chat_cooldown_max_seconds`.

Бот — фильтры:
- `bot/routers/notification_settings.py` — точка входа «фильтр по трейдам» без
  истории: префилл `operation_type='trade'`, суммы и актива из последней сделки.
- `bot/middleware/notification_activity.py` — новый callback в whitelist рядом с
  `create_filter_from:` (строка 54).
- `bot/langs/{ru,en}.json` — строки бандла (`info_trade_bundle_*`). Остальные языки
  наследуют `en` через fallback в `LocalizationService.get_text`, поэтому дублировать
  ключи в `ua/me/hy/am` не нужно.

Тесты:
- `bot/tests/infrastructure/test_notification_coordinator.py` — парковка чата,
  запрет отправки в припаркованный чат, unpark по истечении.
- `bot/tests/infrastructure/test_notification_redis_store.py` — атомарность
  park/unpark, темп отправки.
- `bot/tests/infrastructure/test_notification_webhook.py` — 93 трейда в одной tx
  → одно сообщение; фильтр гасит dust до бандла; переполнение → X строк + «ещё N»
  + ссылка на транзакцию.
- `bot/tests/routers/test_notification_settings.py` — создание трейд-фильтра без
  истории.

Документация:
- `adr/0001-delayed-blockchain-notification-delivery.md` — дополнение: исходящая
  ограничение частоты (темп отправки) и cooldown — зона координатора.
- `docs/runbooks/notification-flood.md` (новый) — как распознать, что делать
  (парковка/пауза, не рестарт), чего не делать.

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> «правки разрешаю. с чего ничинать не знаю, надо оба сдеать» — разрешение дано
> после перечисления путей в чате; решения 1-11 согласованы (ответы на пункты
> 3.5, 1.2, 5.1, 5.2, 5.3), ссылка `/transaction/{hash}` подтверждена работающей,
> план создан по ответу «++».

## Change Plan

1. [x] `notification_redis_store.py` + `notification_coordinator.py`: cooldown-ключ
   `notification:cooldown:{user}`, атомарный `park_chat`, ключ темпа
   `notification:pace:{user}`, `reserve_send_slot` перед каждой отправкой и правкой
   разметки (Lua + fallback без EVAL).
2. [x] `middleware/retry.py`: `no_inline_rate_limit_sleep()` — 429 больше не спит
   inline, а поднимает `ChatRateLimitedError`; координатор паркует чат.
3. [x] `notification_service.py` + `notification_utils.py`: бандл трейдов по tx
   (фильтр до бандла), `visible_text_length`, X = 15, «…и ещё N», ссылка на
   транзакцию; одна сделка сохраняет прежний текст.
4. [x] `config_reader.py`: `notification_chat_min_interval_seconds`,
   `notification_chat_cooldown_max_seconds`, `notification_bundle_max_lines`.
5. [x] `notification_settings.py` + langs: кнопка `add_trade_filter` (фильтр по
   трейдам без истории, префилл суммы из последней сделки) и решение 11 —
   `_filterable_sides` в `notification_service.py`: фильтр по трейду срабатывает
   на любой стороне. `notification_activity.py` править не потребовалось:
   `add_trade_filter` — точный callback, а не префикс флоу.
6. [x] Тесты: `test_notification_coordinator.py` (парковка, темп, потолок cooldown),
   `test_notification_redis_store.py` (park/pace на fakeredis), `test_notification_webhook.py`
   (93 фила в одной tx → одно сообщение, фильтр до бандла, лимит видимых символов).
   Lua-скрипты дополнительно проверены вручную на Redis 7.
7. [x] Docs: дополнение «Amendment 2026-10-30: outbound chat speed» в ADR-0001 и
   новый `docs/runbooks/notification-flood.md` (+ строка в README рунбуков).
8. [x] Прогнать `just check`: fmt + ruff + `mypy core` + 983 теста + arch-test
   зелёные после пересборки `.venv` (`uv sync --all-packages --all-groups`).

## Risks / Open Questions

- **Риск: смена UX уведомлений.** Бандл меняет привычный текст для мейкера: одна
  сделка остаётся как есть, несколько в одной tx — сводка. Нужен явный ответ
  пользователя, устраивает ли сводка вместо построчных сообщений.
- **Риск: `MESSAGE_TOO_LONG` — сейчас poison pill.** `TelegramBadRequest` в
  координаторе удаляет сообщение из очереди без следа; бандл обязан укладываться в
  лимит, иначе потеря события. Проверяется тестом на граничные X.
- **Риск: доставка может отставать.** Темп отправки с минимальным интервалом 1 с даёт
  потолок ~60 сообщений в минуту на чат. Дропа нет (решение 10), значит при
  превышении растёт только задержка. Нужен алерт: голова очереди старше N минут или
  глубина очереди выше M → предупредить админа, а не молча копить.
- **Вопрос: `retry_after` до 2430 s при приватном чате.** Похоже на локальный Bot API
  server (`bot/start.py:325`, `is_local=True`). Если окна ставит он, а не Telegram,
  потолок cooldown надо согласовать с его семантикой.
- **Закрыто: семантика фильтра у мейкера.** Решение 11 — совпадение по любой стороне
  сделки, сумма берётся со стороны совпадения.
- **Риск: смена notification_id у мейкера.** Бандл использует
  `{tx}:trade_bundle:0:{user}`, тогда как до деплоя было `{tx}:trade:{i}:{user}`.
  Событие, стоящее в очереди в момент выката, может быть доставлено повторно.
- **Не входит в план:** GlitchTip/Sentry (пользователь: не трогаем), Emoji/тексты
  уведомлений, дедуп-сет (растёт монотонно, но объём приемлемый).

## Verification

- `just check` — зелёный.
- Сценарий инцидента: payload с 93 трейдами в одной tx → ровно одно сообщение,
  видимая длина ≤ 4096, в шапке ссылка `/transaction/{hash}`, остаток подписан
  «…и ещё 78».
- Фильтр: `trade` + `min_amount` гасит dust-трейды мейкера до попадания в бандл.
- Cooldown: искусственный `retry_after=279` → чат припаркован, отправок в него нет,
  другие чаты доставляются; после срока доставка возобновляется без 429-шторма.
- Логи: `notification_chat_parked`, `notification_bundle_delivered` с числом
  событий, отсутствие роста `retry_after` по одному и тому же чату.
