# 2026-10-04-usdt-limit-admin-cmd: Admin command to temporarily raise USDT limits until restart

## Context

Владельцу нужно временно повышать `max_usdt_sum` (ввод/вывод USDT,
`bot/routers/inout.py:72`, константа 500) руками в коде и деплоем — это
единовременно неудобно. Решение: админ-команда `/usdt_limit <сумма>`
меняет runtime-переменную до рестарта бота (без даты/TTL — после
рестарта лимит возвращается к константе). Команда должна и читать
текущий лимит, и устанавливать новый. Стиль — как остальные админ-команды
в `bot/routers/admin.py` (доступ только `itolstov`).

## Files/Directories To Change

- `bot/routers/admin.py`
- `bot/tests/routers/test_admin.py`
- `docs/exec-plans/active/2026-10-04-2026-10-04-usdt-limit-admin-cmd.md`
  (жизненный цикл плана)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User said: «кончено коменда нахуй мне на сервер лазить. и не нужно дату,
> до рестарта» — approving an admin command (no server access, no TTL).
> Files named by the agent and confirmed implicitly by the user's request
> to implement the feature.

## Change Plan

1. [x] `bot/routers/inout.py:72` — `max_usdt_sum = 500` остаётся единственной
       переменной лимита; все 4 точки проверки читают её (`inout.py:175,269,410,634`).
       (Первоначально завёл алиас `usdt_max_sum_limit` — убрал по решению
       владельца: лишняя сущность.)
2. [x] `bot/routers/admin.py:883-906` — команда `/usdt_limit`: без аргумента
       показывает `inout.max_usdt_sum`, с аргументом ставит `inout.max_usdt_sum = N`;
       валидация положительного целого; гард
       `message.from_user.id not in config.admins` + строка в `/help`
       (`admin.py:831`).
3. [x] `bot/tests/routers/test_admin.py:418-484` — 3 теста: просмотр,
       установка 1000 и возврат к дефолту, отказ `-5`/`abc`.
4. [x] `just test-fast` 477 passed; `just lint` (ruff + mypy core) зелёный.

## Risks / Open Questions

- Runtime-переменная живёт до рестарата процесса — by design (owner
  requested "до рестарта").
- `show_max_sum` для ввода дополнительно ограничивается балансом USDM
  мастера — команде нет нужды это обходить.

## Verification

- `uv run pytest bot/tests/routers/test_admin.py -q`
- `/usdt_limit` → показывает 500; `/usdt_limit 1000` → подтверждение;
  `/usdt_limit` → 1000.