# Обзор проекта

## Назначение
Проект — Telegram-бот на Aiogram 3.x для управления криптокошельками и операциями в основном в сети Stellar, с дополнительной поддержкой TRON/TON и интеграциями внешних сервисов. Поддерживаются создание и импорт кошельков, баланс/транзакции, чеки, обмены, работа с URI (web+stellar), а также админские и мониторинговые функции.

## Ключевые входные точки и жизненный цикл
- `start.py` — единая точка запуска: инициализация бота, Dispatcher, Redis storage для FSM, брокера FastStream (Redis), планировщика APScheduler, DI-контекста `AppContext`, регистрация middleware и роутеров, запуск фоновых воркеров.
- `start.sh` — подготовка виртуального окружения и запуск `start.py`.

## Архитектура и слои
- `core/` — доменная модель (entities/value_objects), интерфейсы репозиториев/сервисов и use-case’ы (wallet, trade, payment, cheque, stellar, user).
- `infrastructure/` — реализация инфраструктуры: репозитории SQLAlchemy, сервисы (stellar, encryption, localization), фабрики use-case’ов, планировщик, мониторинг блокчейна, воркеры и утилиты.
- `routers/` — обработчики Aiogram по функциональным потокам (кошельки, send/swap/trade, чеки, TON, URI, админка, уведомления, мониторинг).
- `middleware/` — DB-сессии, логирование, throttling, retry, обработка устаревших кнопок, DI (AppContext, localization).
- `db/` — пул соединений и модели/запросы (SQLAlchemy).
- `other/` — кросс-срезовые утилиты (config reader, lang tools, stellar/tron helpers, FastStream broker и WalletConnect-логика).
- `keyboards/` — генерация клавиатур.
- `langs/` — локализация (JSON).

## Сервисы и зависимости
- `AppContext` передает зависимости в роутеры: `bot`, `db_pool`, `localization_service`, `repository_factory`, `stellar_service`, `encryption_service`, `use_case_factory`, очереди и диспетчер.
- `LocalizationService` загружает JSON локализации и используется middleware для текстов.
- Репозитории создаются через `SqlAlchemyRepositoryFactory`, use-case’ы через `UseCaseFactory`.
- Redis используется и для FSM storage, и для FastStream брокера.

## Планировщик и фоновые воркеры
- APScheduler настраивается в `infrastructure/scheduler/job_scheduler.py`.
- Фоновые задачи: `cheque_worker`, `log_worker`, `events_worker`, `usdt_worker` и обработчики мониторинга блокчейна.
- WalletConnect-подобная логика подписи реализована через FastStream брокер в `other/faststream_tools.py`.

## Роутеры и ключевые функции
Основные направления:
- управление кошельками (создание, импорт, переключение, read-only режимы),
- отправка/получение средств, подпись и проверка транзакций,
- обмены и торговые операции (swap/trade),
- чеки, фестивальные сценарии, BSN,
- обработка Stellar URI и кнопок возврата (`return_url`),
- TON/USDT сценарии, админские и мониторинговые функции.

## Локализация
- Ключи хранятся в коде, значения — в `langs/*.json`.
- Используется HTML-разметка в сообщениях (не Markdown).
- Язык пользователя хранится в БД и в оперативной памяти; fallback на английский.

## Мониторинг и логирование
- Sentry подключается в `start.py`.
- Логирование — через `loguru.logger`.
- Таймауты и ретраи вынесены в middleware/утилиты.

## Безопасность
- Конфигурация читается из `.env` через `other/config_reader.py`.
- Приватные ключи шифруются, операции с ключами проходят через сервисы.
- Есть защита от устаревших кнопок и throttling.

## Тестирование
- Правила тестов и naming — в `tests/README.md` (обязательно к прочтению перед изменениями).
- Рекомендуемый запуск: `uv run pytest tests/`.
