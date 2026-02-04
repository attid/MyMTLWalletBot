# Биометрическое подписание — Дизайн

## Часть 1: Цели и ограничения

**Цель:** Добавить возможность подписывать транзакции локально на устройстве пользователя, используя биометрию (мобильные) или пароль (десктоп). Секретный ключ никогда не попадает на сервер.

**Для кого:**
- Пользователи, которые импортируют свой ключ (не спонсорские кошельки)
- Параноики, которые не хотят хранить ключ на сервере
- ~40% аудитории на десктопе тоже поддерживаем

**Ключевые ограничения:**
- Секретный ключ хранится только на устройстве пользователя
- Сервер никогда не видит и не передаёт секретный ключ
- Нет fallback — пользователь сам отвечает за бэкап seed
- Bot Server не принимает входящие соединения

**Что НЕ входит в MVP:**
- TOTP + серверный ключ шифрования (на будущее)
- Миграция существующих ключей с сервера (юзер удаляет вручную и импортирует заново)

**Операции:**
- Все операции требующие подписи поддерживаются
- Для тестирования начинаем с send

## Часть 2: Архитектура серверов

```
┌─────────────────────────────────────────────────────────────┐
│  Bot Server (закрытый, только ИСХОДЯЩИЕ соединения)          │
│                                                              │
│  - Telegram bot (aiogram)                                    │
│  - Основная БД (Firebird)                                    │
│  - Кошельки, зашифрованные ключи (для PIN/пароль метода)     │
│  - Создаёт unsigned TX → PUSH на Web App Server              │
│  - Забирает signed TX ← PULL с Web App Server                │
│  - Отправляет signed TX в Stellar network                    │
│  - Никаких входящих соединений                               │
└─────────────────────────────────────────────────────────────┘
           │                              ▲
           │ push (outgoing)              │ poll/subscribe (outgoing)
           ▼                              │
┌─────────────────────────────────────────────────────────────┐
│  Web App Server (публичный)                                  │
│                                                              │
│  - Статика (HTML/JS/CSS) — Telegram Mini App                 │
│  - Минимальный API (FastAPI или аналог)                      │
│  - Redis — хранение pending TX + брокер (FastStream)         │
│  - Порт 443 открыт для пользователей                         │
│  - Принимает unsigned TX от бота                             │
│  - Отдаёт unsigned TX пользователю                           │
│  - Принимает signed TX от пользователя                       │
│  - Уведомляет бота о готовности через FastStream             │
└─────────────────────────────────────────────────────────────┘
```

**Коммуникация Bot ↔ Web App Server (только через FastStream/Redis):**
- Bot публикует unsigned TX в Redis через FastStream
- Bot подписывается на события tx_signed через FastStream
- Когда TX подписан, Web App Server публикует событие
- Bot получает событие и читает signed_xdr из Redis

## Часть 3: Web App — структура и стек

**Репозиторий:** Отдельная репа (например `mmwb_webapp`)
- Независимый деплой
- Разные стеки не мешают друг другу
- Чистое разделение ответственности

**Стек:**
- **Backend:** Python + FastAPI + FastStream (Redis)
- **Frontend:** Vanilla HTML + JS (без фреймворков)
- **Telegram:** @telegram-apps/sdk для Mini App API
- **Stellar:** stellar-sdk (JS) для подписания в браузере
- **Storage:** Telegram BiometricManager (мобильные), localStorage + Web Crypto (десктоп)

**Структура репозитория:**
```
mmwb_webapp/
├── app/
│   ├── main.py              # FastAPI app
│   ├── api/                 # endpoints
│   ├── broker/              # FastStream handlers
│   ├── static/
│   │   ├── js/
│   │   │   ├── import.js
│   │   │   ├── sign.js
│   │   │   └── common.js
│   │   └── css/
│   │       └── style.css
│   └── templates/
│       ├── import.html
│       └── sign.html
├── Dockerfile
├── docker-compose.yml       # app + redis
└── requirements.txt
```

**Деплой:** Docker Compose с двумя сервисами: app (FastAPI), redis

## Часть 4: Хранение ключа и модель безопасности

**Два режима хранения (выбирается автоматически по возможностям):**

**Режим 1 — Биометрия (если доступна):**
- Ключ хранится в Telegram BiometricManager
- Размер: до 256 байт (Stellar seed 56 символов — влезает)
- Разблокировка: TouchID / FaceID / отпечаток / Windows Hello
- При переустановке Telegram — данные теряются

**Режим 2 — Пароль (если биометрия недоступна):**
- Ключ шифруется паролем пользователя
- Шифрование: AES-256-GCM через Web Crypto API
- Key derivation: PBKDF2 с высоким числом итераций (100k+)
- Хранение: localStorage браузера
- При очистке данных браузера — ключ теряется

**Общие правила:**
- Сервер никогда не видит секретный ключ
- Пользователь обязан хранить бэкап seed самостоятельно
- При настройке показываем предупреждение о рисках

**Что хранится где:**
| Данные | Биометрия | Пароль |
|--------|-----------|--------|
| Секретный ключ | BiometricManager | localStorage (encrypted) |
| Ключ шифрования | Нет | Вводится каждый раз |

## Часть 5: Flow подписания транзакции

```
Пользователь                    Bot Server                 Web App Server              Web App (браузер)
     │                              │                            │                            │
     │── /send 100 XLM to GXXX ────>│                            │                            │
     │                              │                            │                            │
     │<── "Подтвердите: ..."  ──────│                            │                            │
     │    [Кнопка: Подписать]       │                            │                            │
     │                              │                            │                            │
     │                              │══ FastStream: tx_pending ══>│                            │
     │                              │   {tx_id, unsigned_xdr}     │── saves to Redis ─────────>│
     │                              │                            │                            │
     │── клик "Подписать" ─────────────────────────────────────────────────────────────────────>│
     │   (открывает Web App                                      │                            │
     │    с ?startapp=tx_abc123)                                 │                            │
     │                              │                            │                            │
     │                              │                            │<── GET /tx/{tx_id} ────────│
     │                              │                            │── {unsigned_xdr, meta} ───>│
     │                              │                            │                            │
     │                              │                            │         [биометрия/пароль] │
     │                              │                            │         [stellar-sdk.sign] │
     │                              │                            │                            │
     │                              │                            │<── POST /tx/{tx_id}/signed │
     │                              │                            │    {signed_xdr}            │
     │                              │                            │                            │
     │                              │<══ FastStream: tx_signed ═══│                            │
     │                              │                            │                            │
     │                              │── HGET tx:{tx_id} signed_xdr (Redis) ──────────────────>│
     │                              │<── {signed_xdr} ────────────────────────────────────────│
     │                              │                            │                            │
     │                              │── submit to Stellar ───────────────────────────────────────>
     │                              │                            │                            │
     │<── "Успешно отправлено!" ────│                            │                            │
```

**Таймауты:**
- TX хранится в Redis с TTL (например 10 минут)
- Если не подписан за это время — истекает
- Bot показывает "Время истекло, попробуйте снова"

## Часть 6: Flow импорта ключа (при первом подписании)

**Сценарий: у пользователя read-only кошелёк, он пытается подписать транзакцию**

```
Пользователь                    Bot                        Web App (браузер)
     │                              │                            │
     │── /send 100 XLM to GXXX ────>│                            │
     │   (кошелёк read-only)        │                            │
     │                              │                            │
     │<── "Подтвердите: ..."        │                            │
     │    [Кнопка: Подписать]       │                            │
     │                              │                            │
     │── клик "Подписать" ─────────────────────────────────────>│
     │   (первый раз на этом устройстве)                        │
     │                              │                            │
     │                              │              [Ключ не найден локально]
     │                              │              [Проверка: есть биометрия?]
     │                              │                            │
     │<─────────────────────────────────── "Выберите способ хранения:"
     │                              │              "[Биометрия]  [Пароль]"
     │                              │                            │
     │── выбирает ─────────────────────────────────────────────>│
     │                              │                            │
     │<─────────────────────────────────── "Введите секретный ключ"
     │                              │              "⚠️ Сохраните бэкап!"
     │                              │                            │
     │── вводит seed ──────────────────────────────────────────>│
     │                              │                            │
     │                              │              [Валидация: seed → public key]
     │                              │              [Проверка: совпадает с адресом кошелька?]
     │                              │                            │
     │                              │              [Биометрия: подтверди TouchID]
     │                              │              [Пароль: введи пароль]
     │                              │                            │
     │── подтверждает ─────────────────────────────────────────>│
     │                              │                            │
     │                              │              [Сохраняем ключ]
     │                              │              [Подписываем TX]
     │                              │                            │
     │                              │<── POST /tx/{tx_id}/signed │
     │                              │                            │
     │<── "Успешно отправлено!" ────│                            │
```

**Следующие подписания на том же устройстве:**
- Ключ уже сохранён
- Сразу биометрия/пароль → подпись

**Новое устройство:**
- Ключ не найден → повторяем setup
- Каждое устройство настраивается отдельно

**Опционально: тестовая транзакция**
- После первого импорта предложить: "Отправить 1 XLM себе для проверки?"
- Убеждаемся что всё работает

## Часть 7: Структура данных в Redis

**Pending Transaction (Hash):**
```
Key: tx:{tx_id}
TTL: 600 секунд (10 минут)

Fields:
  user_id        - Telegram user ID (для валидации)
  wallet_address - публичный адрес кошелька (GXXX...)
  unsigned_xdr   - XDR транзакции без подписи
  memo           - описание для пользователя ("Отправка 100 XLM на GXXX...")
  created_at     - timestamp создания
  status         - pending | signed | expired | error
  signed_xdr     - XDR с подписью (появляется после подписания)
  error          - текст ошибки (если status=error)
```

**Генерация tx_id:**
- Формат: `{user_id}_{random_uuid}` например `123456_a1b2c3d4`
- UUID для уникальности, user_id для быстрой валидации

**Redis Stream для уведомлений:**
```
Stream: tx_signed_events
Entry:
  tx_id    - ID подписанной транзакции
  user_id  - для роутинга на нужный инстанс бота
```

**Почему Hash, а не просто String:**
- Можно атомарно обновлять отдельные поля (status, signed_xdr)
- Легко добавить поля в будущем
- Bot может проверить status без парсинга всего объекта

## Часть 8: API и FastStream контракты

**FastStream (Bot ↔ Redis):**

```python
# Бот публикует новую TX
Channel: tx_pending
Message: {
    tx_id: str,
    user_id: int,
    wallet_address: str,
    unsigned_xdr: str,
    memo: str
}

# Web App публикует когда TX подписана
Channel: tx_signed
Message: {
    tx_id: str,
    user_id: int
}

# Бот слушает tx_signed, затем читает из Redis Hash:
#   HGET tx:{tx_id} signed_xdr
```

**HTTP API (только для Web App в браузере):**

```
GET /api/tx/{tx_id}
  Headers: X-Telegram-Init-Data: <initData>
  Response: { unsigned_xdr, memo, wallet_address, status }
  Errors:
    403 - user_id из initData не совпадает с TX
    404 - TX не найден или истёк
    410 - TX уже подписан

POST /api/tx/{tx_id}/signed
  Headers: X-Telegram-Init-Data: <initData>
  Body: { signed_xdr }
  Response: { success: true }
  Errors:
    403 - user_id не совпадает
    400 - невалидный XDR или подпись
    404 - TX не найден
    410 - TX истёк
```

**Валидация Telegram InitData:**
- Telegram передаёт в Web App `initData` с подписью
- Сервер проверяет HMAC подпись через bot token
- Извлекает `user_id` — это гарантия что запрос от правильного юзера

**Кто что делает:**
| Действие | Механизм |
|----------|----------|
| Бот создаёт TX | FastStream → Redis Hash |
| Браузер читает TX | HTTP GET |
| Браузер отправляет подпись | HTTP POST → Redis Hash |
| Web App уведомляет бота | FastStream tx_signed |
| Бот забирает signed_xdr | Redis HGET напрямую |

## Часть 9: Изменения в mmwb_bot

**Новое поле в БД (таблица wallets или users):**
```
signing_mode: enum('server', 'local') default 'server'
```
- `server` — ключ на сервере, подписываем как сейчас
- `local` — ключ на устройстве, открываем Web App

**Новый флоу в роутерах подписания:**

```python
# Псевдокод для любой операции требующей подписи (send, swap, etc.)

async def handle_sign_request(user, tx):
    wallet = get_current_wallet(user)

    if wallet.signing_mode == 'server':
        # Текущая логика — подписываем на сервере
        signed = sign_with_server_key(tx, wallet)
        submit(signed)

    elif wallet.signing_mode == 'local':
        # Новая логика — отправляем в Web App
        tx_id = await publish_pending_tx(user, wallet, tx)
        await send_webapp_button(user, tx_id)
        # Ждём события tx_signed через FastStream
```

**Что менять:**
| Файл/модуль | Изменение |
|-------------|-----------|
| `db/models` | Добавить поле `signing_mode` |
| `core/entities` | Добавить в Wallet entity |
| `routers/send.py` | Ветвление по signing_mode |
| `routers/swap.py` | Аналогично |
| `routers/trade.py` | Аналогично |
| `other/faststream_tools.py` | Handlers для tx_pending, tx_signed |
| `keyboards/` | Кнопка Web App с параметром tx_id |

**Новый воркер:**
```
infrastructure/workers/signing_worker.py
  - Слушает tx_signed
  - Забирает signed_xdr из Redis
  - Отправляет в Stellar
  - Уведомляет пользователя о результате
```

## Часть 10: Обработка ошибок в Web App

**Принцип:** Все ошибки показываем inline в UI (никаких alert). Красный блок с текстом + кнопка действия.

**Ошибки API:**
| Код | Текст | Действие |
|-----|-------|----------|
| 404 | "Транзакция не найдена или истекла" | Кнопка "Закрыть" |
| 403 | "Нет доступа к этой транзакции" | Кнопка "Закрыть" |
| 410 | "Транзакция уже подписана" | Кнопка "Закрыть" |
| 5xx | "Ошибка сервера" | Кнопка "Повторить" |

**Ошибки импорта ключа:**
| Ситуация | Текст | Действие |
|----------|-------|----------|
| Невалидный seed | "Неверный формат ключа" | Остаёмся на форме ввода |
| Public key не совпадает | "Ключ не соответствует кошельку {GXXX...}" | Остаёмся на форме |

**Ошибки биометрии/пароля:**
| Ситуация | Текст | Действие |
|----------|-------|----------|
| Отмена биометрии | — | Показываем кнопку "Повторить" |
| Биометрия недоступна | "Биометрия недоступна" | Переключаем на режим пароля |
| Неверный пароль | "Неверный пароль" | Остаёмся на форме |

**Сеть:**
| Ситуация | Текст | Действие |
|----------|-------|----------|
| Нет соединения | "Нет соединения с сервером" | Кнопка "Повторить" |

**UI компонент ошибки:**
```html
<div class="error-block">
  <span class="error-text">Текст ошибки</span>
  <button class="error-action">Действие</button>
</div>
```

## Часть 11: UI экраны Web App

**Экран 1 — Подписание (ключ уже есть):**
```
┌─────────────────────────────┐
│                             │
│  Подтвердите транзакцию     │
│                             │
│  ┌───────────────────────┐  │
│  │ Отправка              │  │
│  │ 100 XLM               │  │
│  │ → GXXX...XXXX         │  │
│  └───────────────────────┘  │
│                             │
│  [ Подписать ]              │
│                             │
│  Отмена                     │
└─────────────────────────────┘
```
- Клик "Подписать" → биометрия или запрос пароля
- "Отмена" → закрывает Mini App

**Экран 2 — Ввод пароля (режим пароля):**
```
┌─────────────────────────────┐
│                             │
│  Введите пароль             │
│                             │
│  ┌───────────────────────┐  │
│  │ ••••••••              │  │
│  └───────────────────────┘  │
│                             │
│  [ Подтвердить ]            │
│                             │
└─────────────────────────────┘
```

**Экран 3 — Импорт ключа (первый раз):**
```
┌─────────────────────────────┐
│                             │
│  Настройка подписания       │
│                             │
│  Кошелёк: GXXX...XXXX       │
│                             │
│  ⚠️ Ключ хранится только    │
│  на вашем устройстве.       │
│  Сохраните бэкап!           │
│                             │
│  ┌───────────────────────┐  │
│  │ Секретный ключ (seed) │  │
│  │ S...                  │  │
│  └───────────────────────┘  │
│                             │
│  Способ защиты:             │
│  ○ Биометрия (рекомендуем)  │
│  ○ Пароль                   │
│                             │
│  [ Сохранить ]              │
│                             │
└─────────────────────────────┘
```
- Если биометрия недоступна — показываем только пароль
- После "Сохранить" → запрос биометрии или ввод пароля

**Экран 4 — Создание пароля (при импорте):**
```
┌─────────────────────────────┐
│                             │
│  Создайте пароль            │
│                             │
│  ┌───────────────────────┐  │
│  │ Пароль                │  │
│  └───────────────────────┘  │
│  ┌───────────────────────┐  │
│  │ Повторите пароль      │  │
│  └───────────────────────┘  │
│                             │
│  [ Сохранить ]              │
│                             │
└─────────────────────────────┘
```

**Экран 5 — Успех:**
```
┌─────────────────────────────┐
│                             │
│         ✓                   │
│                             │
│  Транзакция подписана       │
│                             │
│  Можете закрыть это окно    │
│                             │
└─────────────────────────────┘
```
- Автоматически закрывается через 2 сек или по тапу

**Стилизация:**
- Telegram Mini App тема (светлая/тёмная автоматически)
- Используем CSS переменные Telegram: `var(--tg-theme-bg-color)`, `var(--tg-theme-text-color)`, etc.
- Минимум кастомных стилей

## Часть 12: Структура монорепы

**Решение:** Монорепа с модулями. Бот переезжает в подпапку.

```
mmwb_bot/
├── bot/                      — текущий код бота
│   ├── routers/
│   ├── core/
│   ├── infrastructure/
│   ├── middleware/
│   ├── db/
│   ├── keyboards/
│   ├── langs/
│   ├── other/
│   ├── tests/
│   ├── start.py
│   └── pyproject.toml        — зависимости бота
│
├── webapp/                   — новый Web App
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── broker/
│   │   ├── static/
│   │   └── templates/
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml        — зависимости webapp
│
├── shared/                   — общий код
│   ├── schemas.py            — Pydantic модели для FastStream
│   ├── constants.py          — имена каналов, TTL, ключи Redis
│   └── pyproject.toml
│
├── docker-compose.yml        — bot + webapp + redis
├── pyproject.toml            — workspace root (uv/poetry)
└── README.md
```

**shared/schemas.py:**
```python
from pydantic import BaseModel

class PendingTxMessage(BaseModel):
    tx_id: str
    user_id: int
    wallet_address: str
    unsigned_xdr: str
    memo: str

class TxSignedMessage(BaseModel):
    tx_id: str
    user_id: int
```

**shared/constants.py:**
```python
# FastStream channels
CHANNEL_TX_PENDING = "tx_pending"
CHANNEL_TX_SIGNED = "tx_signed"

# Redis keys
REDIS_TX_PREFIX = "tx:"
REDIS_TX_TTL = 600  # 10 минут

# Redis Hash fields
FIELD_USER_ID = "user_id"
FIELD_WALLET_ADDRESS = "wallet_address"
FIELD_UNSIGNED_XDR = "unsigned_xdr"
FIELD_MEMO = "memo"
FIELD_STATUS = "status"
FIELD_SIGNED_XDR = "signed_xdr"
FIELD_CREATED_AT = "created_at"
FIELD_ERROR = "error"

# TX statuses
STATUS_PENDING = "pending"
STATUS_SIGNED = "signed"
STATUS_EXPIRED = "expired"
STATUS_ERROR = "error"
```

**Миграция существующего кода:**
1. Создать структуру папок
2. `git mv` всех файлов бота в `bot/`
3. Обновить импорты (IDE refactor или скрипт)
4. Обновить `start.sh`, CI/CD, Dockerfile

## Часть 13: План тестирования (сторона бота)

**Цель:** Убедиться что бот готов к интеграции до того как webapp существует.

### Unit тесты

**1. Публикация TX в FastStream:**
```python
# tests/test_signing_flow.py

async def test_publish_pending_tx():
    """TX публикуется с правильной структурой"""
    broker = MockBroker()

    tx_id = await publish_pending_tx(
        user_id=123,
        wallet_address="GXXX...",
        unsigned_xdr="AAAA...",
        memo="Отправка 100 XLM"
    )

    assert broker.published[CHANNEL_TX_PENDING] == PendingTxMessage(
        tx_id=tx_id,
        user_id=123,
        wallet_address="GXXX...",
        unsigned_xdr="AAAA...",
        memo="Отправка 100 XLM"
    )
```

**2. Обработка события tx_signed:**
```python
async def test_handle_tx_signed():
    """Бот забирает подпись и отправляет в Stellar"""
    redis = MockRedis()
    redis.hset(f"tx:abc123", "signed_xdr", "SIGNED_XDR...")
    stellar = MockStellarService()

    await handle_tx_signed(TxSignedMessage(tx_id="abc123", user_id=123))

    assert stellar.submitted == ["SIGNED_XDR..."]
```

**3. Ветвление по signing_mode:**
```python
async def test_signing_mode_server():
    """signing_mode=server использует серверный ключ"""
    wallet = Wallet(signing_mode="server", secret_key="S...")
    # ... проверяем что вызывается sign_with_server_key

async def test_signing_mode_local():
    """signing_mode=local публикует в FastStream"""
    wallet = Wallet(signing_mode="local")
    # ... проверяем что вызывается publish_pending_tx
```

**4. Таймаут TX:**
```python
async def test_tx_timeout():
    """Бот уведомляет пользователя об истечении TX"""
    # Эмулируем что TX истёк (нет в Redis)
    # Проверяем что пользователь получает сообщение
```

### Integration тесты

**С реальным Redis (testcontainers или fakeredis):**
```python
async def test_full_signing_flow():
    """E2E: публикация → подпись → отправка"""
    # 1. Бот публикует TX
    tx_id = await publish_pending_tx(...)

    # 2. Эмулируем webapp: пишем signed_xdr в Redis
    redis.hset(f"tx:{tx_id}", "signed_xdr", "SIGNED...")
    redis.hset(f"tx:{tx_id}", "status", "signed")

    # 3. Публикуем tx_signed (как это делает webapp)
    await broker.publish(CHANNEL_TX_SIGNED, TxSignedMessage(...))

    # 4. Проверяем что бот отправил в Stellar
    assert stellar.submitted == ["SIGNED..."]
```

### Что НЕ тестируем на стороне бота:
- Биометрию / Web Crypto (это webapp)
- Telegram InitData валидацию (это webapp)
- UI экраны (это webapp)

### Порядок имплементации:
1. ✅ Создать структуру монорепы
2. ✅ Написать shared/ (schemas, constants)
3. ✅ Написать тесты для бота (red)
4. ✅ Имплементировать логику бота (green)
5. ⏳ Потом: webapp

## Часть 14: План изменений в боте

### Этап 1: Реструктуризация репозитория

**1.1. Создать структуру папок:**
```bash
mkdir -p bot webapp shared
```

**1.2. Переместить код бота:**
```bash
git mv routers/ bot/
git mv core/ bot/
git mv infrastructure/ bot/
git mv middleware/ bot/
git mv db/ bot/
git mv keyboards/ bot/
git mv langs/ bot/
git mv other/ bot/
git mv tests/ bot/
git mv start.py bot/
git mv start.sh bot/
git mv pyproject.toml bot/
git mv uv.lock bot/
# ... и остальные файлы бота
```

**1.3. Обновить импорты:**
- Все `from routers import ...` → `from bot.routers import ...`
- Или настроить `bot/` как пакет и оставить относительные импорты

**1.4. Создать корневой pyproject.toml:**
```toml
[project]
name = "mmwb"
version = "0.1.0"

[tool.uv.workspace]
members = ["bot", "webapp", "shared"]
```

**1.5. Проверить что бот запускается:**
```bash
cd bot && uv run python start.py
```

### Этап 2: Shared модуль

**2.1. shared/pyproject.toml:**
```toml
[project]
name = "mmwb-shared"
version = "0.1.0"
dependencies = ["pydantic>=2.0"]
```

**2.2. shared/schemas.py** — как в части 12

**2.3. shared/constants.py** — как в части 12

**2.4. Добавить зависимость в bot/pyproject.toml:**
```toml
dependencies = [
    "mmwb-shared",
    # ... остальные
]
```

### Этап 3: Модель данных

**3.1. Добавить поле в БД:**
```sql
ALTER TABLE wallets ADD COLUMN signing_mode VARCHAR(10) DEFAULT 'server';
```

**3.2. Обновить SQLAlchemy модель (db/models):**
```python
class Wallet(Base):
    # ... существующие поля
    signing_mode = Column(String(10), default="server")  # 'server' | 'local'
```

**3.3. Обновить entity (core/entities):**
```python
@dataclass
class Wallet:
    # ... существующие поля
    signing_mode: str = "server"
```

**3.4. Обновить репозиторий если нужно**

### Этап 4: FastStream handlers

**4.1. Обновить other/faststream_tools.py:**
```python
from shared.schemas import PendingTxMessage, TxSignedMessage
from shared.constants import CHANNEL_TX_PENDING, CHANNEL_TX_SIGNED, REDIS_TX_PREFIX

async def publish_pending_tx(
    broker,
    redis,
    user_id: int,
    wallet_address: str,
    unsigned_xdr: str,
    memo: str
) -> str:
    """Публикует TX для подписания в Web App"""
    tx_id = f"{user_id}_{uuid4().hex[:8]}"

    # Сохраняем в Redis Hash
    await redis.hset(f"{REDIS_TX_PREFIX}{tx_id}", mapping={
        "user_id": user_id,
        "wallet_address": wallet_address,
        "unsigned_xdr": unsigned_xdr,
        "memo": memo,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat()
    })
    await redis.expire(f"{REDIS_TX_PREFIX}{tx_id}", REDIS_TX_TTL)

    # Публикуем событие
    await broker.publish(
        CHANNEL_TX_PENDING,
        PendingTxMessage(
            tx_id=tx_id,
            user_id=user_id,
            wallet_address=wallet_address,
            unsigned_xdr=unsigned_xdr,
            memo=memo
        )
    )

    return tx_id
```

**4.2. Handler для tx_signed (infrastructure/workers/signing_worker.py):**
```python
@broker.subscriber(CHANNEL_TX_SIGNED)
async def handle_tx_signed(msg: TxSignedMessage, context: AppContext):
    """Обрабатывает подписанную TX"""
    tx_key = f"{REDIS_TX_PREFIX}{msg.tx_id}"

    # Забираем подпись из Redis
    signed_xdr = await context.redis.hget(tx_key, "signed_xdr")
    if not signed_xdr:
        logger.error(f"TX {msg.tx_id}: signed_xdr not found")
        return

    # Отправляем в Stellar
    try:
        result = await context.stellar_service.submit_transaction(signed_xdr)
        await notify_user_success(context.bot, msg.user_id, result)
    except Exception as e:
        await notify_user_error(context.bot, msg.user_id, str(e))

    # Удаляем TX из Redis
    await context.redis.delete(tx_key)
```

### Этап 5: Изменения в роутерах

**5.1. Создать helper для проверки signing_mode:**
```python
# bot/other/signing_helpers.py

async def request_signature(
    user: User,
    wallet: Wallet,
    tx: Transaction,
    memo: str,
    context: AppContext,
    message: Message
):
    """Универсальный метод запроса подписи"""

    if wallet.signing_mode == "server":
        # Текущая логика
        signed = sign_transaction(tx, wallet.secret_key)
        return await submit_and_notify(signed, context, message)

    elif wallet.signing_mode == "local":
        # Новая логика — Web App
        unsigned_xdr = tx.to_xdr()
        tx_id = await publish_pending_tx(
            context.broker,
            context.redis,
            user.id,
            wallet.address,
            unsigned_xdr,
            memo
        )
        await message.answer(
            "Подтвердите транзакцию:",
            reply_markup=webapp_sign_keyboard(tx_id)
        )
        return None  # Результат придёт через FastStream
```

**5.2. Обновить routers/send.py:**
```python
# Вместо прямого подписания:
# signed = sign_transaction(tx, wallet.secret_key)
# await submit(signed)

# Используем helper:
await request_signature(user, wallet, tx, memo, context, message)
```

**5.3. Аналогично для swap.py, trade.py и других**

### Этап 6: Клавиатура Web App

**6.1. keyboards/webapp.py:**
```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

WEBAPP_URL = "https://webapp.example.com"  # из config

def webapp_sign_keyboard(tx_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✍️ Подписать",
            web_app=WebAppInfo(url=f"{WEBAPP_URL}/sign?tx={tx_id}")
        )],
        [InlineKeyboardButton(
            text="Отмена",
            callback_data="cancel_sign"
        )]
    ])
```

### Этап 7: Тесты

**7.1. tests/test_signing_flow.py** — как в части 13

**7.2. Запуск:**
```bash
cd bot && uv run pytest tests/test_signing_flow.py -v
```

### Чеклист готовности бота:

- [ ] Репозиторий реструктурирован (bot/, shared/, webapp/)
- [ ] shared/ содержит schemas.py и constants.py
- [ ] Поле signing_mode добавлено в БД и модели
- [ ] publish_pending_tx() работает
- [ ] handle_tx_signed() работает
- [ ] request_signature() helper создан
- [ ] Роутеры используют request_signature()
- [ ] Web App клавиатура создана
- [ ] Unit тесты проходят
- [ ] Integration тесты проходят
- [ ] Бот запускается и работает в режиме signing_mode=server
