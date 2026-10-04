# 2026-10-04-fix-help-html-brackets: Fix /help: HTML-escaping angle brackets rejected by Telegram

## Context

`/help` перестал отвечать в проде: бот ходит с `parse_mode="HTML"`
(`bot/start.py:292`), а текст `/help` содержал подсказки
`/chequepay <адрес> <сумма>` и `/withdraw <адрес> <сумма> <ассет> [memo]`
(`bot/routers/admin.py`). Telegram считает `<адрес>` невалидным HTML-тегом
и отклоняет сообщение целиком (`MessageTextIsNotFormatted`-класс ошибки) —
юзер видит тишину.

Те же голые `<...>` сидели в usage-подсказках `_handle_payout_command`
(`bot/routers/admin.py:225` и `231`), ломая `/withdraw`/`/chequepay`
при нехватке аргументов той же болезнью.

Регресс-тест: `bot/tests/routers/test_admin.py:398`
(`test_cmd_help_text_has_no_angle_brackets`) — падает при появлении `<`/`>`
в тексте `/help`.

## Files/Directories To Change

- `bot/routers/admin.py`
- `bot/tests/routers/test_admin.py`
- `docs/exec-plans/active/2026-10-04-2026-10-04-fix-help-html-brackets.md`
  (жизненный цикл плана)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User said: "да комить и пуш" — confirming commit+push of the two files
> proposed exactly in the previous message:
> «Жду твоё разрешение на пути, чтобы закоммитить:
> bot/routers/admin.py + bot/tests/routers/test_admin.py».

## Change Plan

1. [x] `bot/routers/admin.py:830-831` — в тексте `/help` заменить
       `<адрес> <сумма> ...` на `[адрес] [сумма] [ассет] [memo]`.
2. [x] `bot/routers/admin.py:225,231` — те же `<...>` в usage-строках
       `/withdraw` и `/chequepay` заменить на `[...]`.
3. [x] `bot/tests/routers/test_admin.py` — добавить
       `test_cmd_help_text_has_no_angle_brackets` (red → green).
4. [x] Прогнать `just test-fast` — 477 passed (21 из test_admin.py).
5. [x] Захуячить коммит с этим планом (пуш выполняет владелец — его абсолютное
       право; пункт пуши ассистенту запрещён и в планы не включается).

## Risks / Open Questions

- Осмысленные HTML-теги в остальных сообщениях admin-роутера
  (`<code>`, `<b>`, `<a href>`) не тронуты — они легитимные.
- Другие команды с голыми `<...>` в текстах могли существовать —
  на момент правки grep по admin.py чистый.

## Verification

- `uv run pytest bot/tests/routers/test_admin.py -q` → 21 passed.
- `just test-fast` → 477 passed.
- Новый тест зелёный, воспроизводит: red до правки (сообщил текст с
  `<адрес>`), green после.