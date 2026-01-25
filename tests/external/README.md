# External Integration Tests

Тесты в этой папке проверяют интеграцию с **внешними сервисами** (Docker контейнеры, внешние API и т.д.).

## Почему отдельно?

- Требуют Docker и могут быть медленными
- Зависят от внешних образов (например, `ghcr.io/montelibero/stellar_notifier`)
- **Автоматически исключаются** из обычного `uv run pytest` через маркер `@pytest.mark.external`

## Как запустить?

```bash
# Обычный pytest - внешние тесты НЕ запускаются
uv run pytest
# Результат: 422 passed, 4 deselected

# Запустить ТОЛЬКО внешние тесты
uv run pytest -m external

# Запустить ВСЕ тесты (включая внешние)
uv run pytest -m ""

# Запустить конкретный файл внешних тестов
uv run pytest tests/external/test_notifier_flow.py

# С verbose
uv run pytest -m external -v
```

## Требования

- Docker должен быть установлен и запущен
- Доступ к интернету для скачивания образов контейнеров
- Свободный порт 8081 для webhook-сервера

## Текущие тесты

### `test_notifier_flow.py`
Тестирует интеграцию с Stellar Notifier service:
- `test_notifier_subscription_isolation` - изоляция подписок между пользователями с разными токенами
- `test_notifier_webhook_delivery` - E2E доставка webhook уведомлений
- `test_nonce_lookup` - проверка nonce в token auth режиме
- `test_nonce_concurrency` - безопасность конкурентной генерации nonce
