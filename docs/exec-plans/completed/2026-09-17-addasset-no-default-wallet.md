# addasset-no-default-wallet: закрыть путь к AddAsset без дефолтного кошелька + убрать трейсбек из лога

## Context

Прод-лог Swarm (docker3), 2026-09-17 10:59:49–11:03:43 UTC: юзер 667006588
10 раз нажал `AddAsset` (7) / `AddAssetExpert` (3); каждый раз
`GetWalletBalance.execute` (core/use_cases/wallet/get_balance.py:48) кидал
`ValueError("No default wallet found for user")`, и middleware
`sentry_error_handler` валила в лог полный трейсбек. Ответ юзеру бот не
отправлял вообще — отсюда повторные нажатия.

Цепочка, подтверждённая кодом:
1. `get_default_wallet` возвращает None только если нет строки
   `default_wallet=1 AND need_delete=0` (sqlalchemy_wallet_repository.py:45-52).
2. При этом меню продолжают работать: `get_start_text` отдаёт "No wallet found"
   (start_msg.py:273-275), `cmd_wallet_setting` и `cmd_manage_assets` не
   проверяют кошелёк и рисуют кнопки AddAsset/AddAssetExpert
   (wallet_setting.py:135-284).
3. Хендлеры `cmd_add_asset_add` (:792) и `cmd_add_asset_expert` (:906) сами
   берут wallet, но допускают None (`is_free = wallet.is_free if wallet else
   False`) и всё равно зовут `balance_use_case.execute(user_id=...)` — падение
   на :812/:920, ровно как в логе.
4. Откуда взялось состояние "нет дефолтного кошелька" — кандидаты (без прод-БД
   не различить): удаление последнего/дефолтного кошелька через
   ChangeWallet → YES_DELETE (common_setting.py:266-291, delete не
   переназначает default и не защищает последний кошелёк);
   `_mark_notification_wallet_deleted` помечает need_delete=1 при бане бота
   (notification_service.py:163-182); удаление аккаунта (manage_user).

## Files/Directories To Change

- `bot/routers/wallet_setting.py` — guard на отсутствие дефолтного кошелька в
  `cmd_manage_assets`, `cmd_add_asset_add`, `cmd_add_asset_expert`
- `bot/tests/routers/test_wallet_setting.py` — регресс-тесты на guard
- `bot/langs/ru.json`, `bot/langs/en.json` — новый ключ `no_wallet_found`
  с призывом /start (выбор пользователя)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> Ревью плана 2026-09-17: fix_scope = «Меню + 2 хендлера», message_text =
> «Новый ключ с /start» (ответы в ask-диалоге).


## Change Plan

1. [x] `cmd_add_asset_add`: если `wallet is None` — короткий
       `logger.warning` + сообщение юзеру + return (до вызова balance use case)
2. [x] `cmd_add_asset_expert`: тот же guard + убрать дубль строки `user_id`
3. [x] `cmd_manage_assets`: без дефолтного кошелька не рендерить кнопки,
       отправить пояснение
4. [x] Регресс-тесты: AddAsset/AddAssetExpert/ManageAssetsMenu без кошелька —
       юзер получает сообщение, ValueError не летит (mock_telegram)
5. [x] `just check-fast` / точечные pytest зелёные

### Follow-up (ревью владельца: сценарий «3 кошелька, дефолт удалён»)

6. [x] Разведены два кейса в `_send_no_wallet_reply`: есть активные кошельки —
       `default_wallet_not_found` (Set active в «Сменить кошелек»), активных
       нет — `no_wallet_found` (добавить кошелек там же). Совет «/start»
       убран: для существующего юзера /start ничего не создаёт
       (common_start.py:96, регистрация только при check_user_lang is None)
7. [x] Тексты `no_wallet_found` в ru/en указывают на «Сменить кошелек»
8. [x] Тесты ветки «активные есть, дефолта нет» для AddAsset и
       ManageAssetsMenu; файл 14 passed

## Verification

- TDD подтверждён: до фикса `test_add_asset_without_default_wallet_shows_hint`
  падал с `ValueError: No default wallet found for user` (воспроизведение),
  после фикса зелёный
- `uv run pytest bot/tests/routers/test_wallet_setting.py` — 14 passed
  (5 новых регресс-тестов; ветка «без кошельков» падала до фикса —
  воспроизведение ValueError)
- `just check-fast` — зелёный (lint, arch-test, docs contract, scope-lock)
- `just test` (первая итерация) — 813 passed, 8 deselected
- `just fmt` прогнан; случайный формат-дрейф в test_web_tools.py /
  test_mtltools.py откачен (вне скоупа)
