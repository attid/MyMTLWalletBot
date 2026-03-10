# 2026-03-10-fix-notification-repo-get-by-id: добавить get_by_id в INotificationRepository

## Контекст

`notification_settings.py:431` вызывал `repo.get_by_id(filter_id)` при action="info",
но метод отсутствовал в `SqlAlchemyNotificationRepository` и в интерфейсе `INotificationRepository`.
Результат: `AttributeError` в runtime при просмотре деталей фильтра.

## План изменений

1. [x] `core/interfaces/repositories.py` — добавить абстрактный метод `get_by_id(filter_id) -> Optional[NotificationFilter]`
2. [x] `infrastructure/persistence/sqlalchemy_notification_repository.py` — реализовать `get_by_id`
3. [x] `just check-fast` проходит (мок `get_by_id` уже был в тестовой фикстуре)

## Верификация

`just check-fast` — 345 тестов, все зелёные.
