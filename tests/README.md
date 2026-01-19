# Testing Guidelines / Правила тестирования

## Принципы ("философия тестов")

### 1. Минимум моков — Максимум реального кода

**Мокать только "последнюю милю":**
- ✅ БД (репозитории, session)
- ✅ Stellar Network (StellarService)
- ✅ Telegram API (bot.send_message)
- ❌ НЕ мокать клавиатуры — пусть отработает реальный код
- ❌ НЕ мокать утилиты (float2str, my_round)
- ❌ НЕ мокать локальную бизнес-логику

```python
# ❌ ПЛОХО: мокаем всё подряд
with patch("routers.swap.jsonpickle.decode"), \
     patch("routers.swap.stellar_get_market_link"), \
     patch("keyboards.common_keyboards.get_return_button"):
    ...

# ✅ ХОРОШО: мокаем только внешние зависимости
mock_app_context.stellar_service.get_balances.return_value = [...]
mock_app_context.repository_factory.get_wallet_repository.return_value = mock_repo
await handler(message, state, session, app_context=mock_app_context)
# Клавиатуры и утилиты работают по-настоящему
```

### 2. Dependency Injection вместо patch()

**Новые тесты должны:**
- Использовать `app_context` для получения зависимостей
- Передавать моки через параметры, а не патчить модули
- Быть устойчивы к рефакторингу импортов

```python
# ❌ ПЛОХО: хрупкий patch по пути модуля
with patch("routers.swap.SqlAlchemyUserRepository") as MockRepo:
    ...

# ✅ ХОРОШО: DI через app_context
mock_app_context = create_mock_app_context()
mock_app_context.repository_factory.get_user_repository.return_value = mock_user_repo
await cmd_swap_sum(message, state, session, app_context=mock_app_context)
```

### 3. Каскадная валидация

Если функция вызывает другую локальную функцию — пусть она отработает.
Тест должен проверять конечный результат, а не промежуточные вызовы.

```python
# ❌ ПЛОХО: мокаем промежуточный вызов
with patch("routers.send.cmd_send_04") as mock:
    await cmd_send_01(...)
    mock.assert_called()  # Тестируем реализацию, а не поведение

# ✅ ХОРОШО: проверяем конечный результат
await cmd_send_01(...)
# Проверяем что отправлено правильное сообщение, правильная клавиатура
assert "expected_text" in sent_message.text
assert len(keyboard.inline_keyboard) == 3
```

---

## Что можно и нужно мокать

| Категория | Мокать? | Почему |
|-----------|---------|--------|
| БД (repositories) | ✅ Да | Внешняя зависимость, медленно |
| Stellar API | ✅ Да | Внешняя сеть, нестабильно |
| Telegram Bot API | ✅ Да | Внешняя сеть |
| config | ⚠️ Иногда | Только если нужны специфичные значения |
| Клавиатуры | ❌ Нет | Локальная логика, пусть работает |
| Утилиты (float2str) | ❌ Нет | Чистые функции, быстрые |
| jsonpickle | ❌ Нет | Локальная сериализация |
| Другие хендлеры | ❌ Нет | Интеграция важна |

---

## Структура теста

```python
@pytest.mark.asyncio
async def test_handler_name(mock_session, mock_callback, mock_state):
    # 1. Arrange: подготовка mock_app_context
    mock_app_context = MagicMock()
    mock_app_context.localization_service.get_text.return_value = "text"
    mock_app_context.repository_factory.get_wallet_repository.return_value = mock_wallet_repo
    mock_app_context.stellar_service.get_balances.return_value = [mock_balance]
    
    # 2. Act: вызов тестируемой функции
    await cmd_handler(mock_callback, mock_state, mock_session, app_context=mock_app_context)
    
    # 3. Assert: проверка результатов
    mock_callback.answer.assert_called_once()
    # Проверяем реальное поведение, не моки
```

---

## Хелпер для создания app_context (conftest.py)

```python
@pytest.fixture
def mock_app_context():
    """Создаёт стандартный mock AppContext для тестов."""
    ctx = MagicMock()
    ctx.localization_service.get_text.return_value = "text"
    ctx.stellar_service = AsyncMock()
    ctx.repository_factory = MagicMock()
    return ctx
```

---

## Миграция существующих тестов

Существующие тесты с `patch()` продолжат работать.
При изменении тестов — переводить на новый подход.

**Приоритет миграции:**
1. Тесты, которые часто ломаются при рефакторинге
2. Тесты с большим количеством patch (>3)
3. Новые тесты для роутеров без покрытия
