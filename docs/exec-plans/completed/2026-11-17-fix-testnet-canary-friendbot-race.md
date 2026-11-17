# fix-testnet-canary-friendbot-race: Testnet canary ждёт появления аккаунта в Horizon

## Context

Ночной workflow `External Integration` (run 44072642758, commit 143ee01) упал на
`bot/tests/external/test_testnet_canary.py::test_friendbot_bootstrap_account_is_reachable`:

- Friendbot вернул `200` для sender и receiver.
- `GET /accounts/{sender}` — 200, `GET /accounts/{receiver}` — `404 Resource Missing`.

Friendbot подтверждает операцию до того, как аккаунт становится виден в Horizon
(нужно закрытие леджера, ~5 c). Тест делает единственный `GET` без ретрая, поэтому
ночной прогон флейкует. Код бота ни при чём: CI-workflow на том же коммите зелёный.

Отдельная проблема: `_wait_for_native_balance_increase` вызывает `_get_account`,
который жёстко падает на любом не-200, так что ретрай ожидания баланса не спасает
от 404 при первом обращении.

## Files/Directories To Change

- `bot/tests/external/test_testnet_canary.py`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "ок давай поправим" (после явного предложения править только
> `bot/tests/external/test_testnet_canary.py`).

## Change Plan

1. [x] `bot/tests/external/test_testnet_canary.py`: добавить
   `_wait_for_account(...)` — поллинг `GET /accounts/{id}` с шагом 1 c и
   таймаутом 30 c; `404` считается «аккаунт ещё не виден», остальные не-200
   валятся как раньше с телом ответа.
2. [x] Использовать `_wait_for_account` в тесте вместо первых двух
   `_get_account` (sender/receiver baseline).
3. [x] В `_wait_for_native_balance_increase` перейти на `_wait_for_account`,
   чтобы 404 внутри цикла не ломал ожидание.
4. [x] Обновить докстринги/комментарии без расширения скоупа (`_get_account`
   удалён — его единственным поведением был assert-first-fetch).
5. [x] Run `just fmt`, `just lint`, `just check-fast` (тесты локально — с
   env из `.github/workflows/external-integration.yml`; без env Settings
   падает при collection, это не связано с правкой).

## Risks / Open Questions

- Таймаут 30 c может не хватить при сильной деградации testnet; при повторных
  флейках поднять до 60 c.
- Тест остаётся сетевым по природе: внешние 5xx от Horizon не ретраятся
  (осознанно, чтобы не маскировать падение testnet).

## Verification

- `just fmt` — 240 files left unchanged.
- `just lint` — ruff + mypy чисто.
- `just arch-test` — все три линтера границ прошли.
- `pytest tests/core tests/infrastructure tests/other -m "not integration"` с env
  из workflow — 712 passed.
- `pytest tests/external/test_testnet_canary.py -m external` с env из workflow —
  1 passed (16.7 s, реальный testnet).
- Дальше — ночной `External Integration` после пуша.
