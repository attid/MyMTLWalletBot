# MyMTLWalletBot

MyMTLWalletBot

## Development & Quality Control

Для поддержания качества кода в проекте используются `ruff` и `mypy`. 
**Рекомендуется запускать их перед каждым коммитом.**

### 1. Проверка стиля и линтинг (Ruff)
Ruff проверяет стиль кода, находит неиспользуемые импорты и потенциальные ошибки.

```bash
# Проверка
uv run ruff check .

# Автоматическое исправление ошибок
uv run ruff check --fix .

# Форматирование кода
uv run ruff format .
```

### 2. Статическая типизация (Mypy)
Mypy проверяет корректность типов данных, предотвращая ошибки `TypeError` и `AttributeError`.

```bash
uv run mypy .
```

## Testing

Run tests using `uv`:

```bash
uv run pytest tests/
```
