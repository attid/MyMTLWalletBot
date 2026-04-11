# fix-notification-detached-instance: Use UPDATE by id when marking wallet deleted on Telegram forbidden

## Context

Продакшен падает при обработке webhook'а notifier, когда пользователь
заблокировал бота:

```
sqlalchemy.exc.InvalidRequestError:
  Object '<MyMtlWalletBot at ...>' is already attached to session '702' (this is '707')
```

Стек: `notification_service.py:881` → `session.add(wallet)` в обработчике
`TelegramForbiddenError` внутри `_send_notification_to_user`.

**Root cause.** В `NotificationService` на строках 408-418 открывается сессия
S1, через неё загружаются wallets, и в том же `async with` блоке для каждого
вызывается `_send_notification_to_user(wallet, ...)`. Wallet ORM-инстанс
остаётся привязан к S1. Внутри обработчика `TelegramForbiddenError` код
открывает новую сессию S3 и делает `session.add(wallet)` — SQLAlchemy
отказывает, т.к. wallet всё ещё tracked первой сессией.

Существующий тест `test_forbidden_notification_marks_wallet_deleted`
использует `MagicMock(spec=MyMtlWalletBot)` — мок не считается "attached",
поэтому баг в тестах не ловится.

## Files/Directories To Change

- `bot/infrastructure/services/notification_service.py`
- `bot/tests/infrastructure/test_notification_webhook.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

## Change Plan

1. [x] Обновить тест `test_forbidden_notification_marks_wallet_deleted` так,
       чтобы он проверял: `session.add` не был вызван, `session.commit`
       был вызван; снять ассерт `wallet.need_delete == 1`.
2. [x] В `notification_service.py`: расширить импорт
       `from sqlalchemy import select` до `from sqlalchemy import select, update`.
3. [x] В `_send_notification_to_user`, в блоке `except TelegramForbiddenError`,
       заменить мутацию `wallet.need_delete = 1` + `session.add(wallet)`
       на прямой UPDATE по `wallet.id`.
4. [x] `just check-fast` проходит (356 tests).
5. [x] Обновления `docs/` не требуется — изменение внутреннее, публичные
       контракты не затронуты.

## Risks / Open Questions

- Если `wallet.id` равен `None` (не должно быть — объект загружен из БД
  через `select(MyMtlWalletBot)...`), UPDATE затронет 0 строк. Это всё
  равно безопаснее текущего падения.
- Мутация `wallet.need_delete = 1` до open second session могла триггерить
  flush S1 на этом же поле. Убираем мутацию вообще — in-memory объект
  остаётся с `need_delete=0`, что ok, т.к. этот экземпляр больше не
  используется после обработки текущей операции.

## Verification

- `uv run pytest bot/tests/infrastructure/test_notification_webhook.py -q`
- `uv run pytest bot/tests/other/test_import_sanity.py -q`
- `just check-fast`
- Expected signal: обновлённый тест зелёный, полный гейт зелёный, падающая
  трасса `InvalidRequestError: already attached to session` в проде не
  воспроизводится при блокировке бота пользователем.
