# 2026-03-10-fix-clear-state-fsm-reset: clear_state должен сбрасывать FSM state

## Контекст

`clear_state()` в `bot/infrastructure/utils/telegram_utils.py` сбрасывала только данные
(`state.set_data(...)`), но НЕ сбрасывала сам FSM-state. Это позволяло пользователю
застрять в состоянии (например `ask_password_set` после незавершённой смены пароля) —
оно сохранялось в Redis и влияло на последующие операции.

В `start_msg.py:200` уже был явный `await state.set_state(None)` перед `clear_state` —
что подтверждало, что проблема была известна, но решалась снаружи.

## План изменений

1. [x] `telegram_utils.py` — добавить `await state.set_state(None)` в конец `clear_state`
2. [x] `start_msg.py` — убрать ставшую дублем `await state.set_state(state=None)` перед вызовом `clear_state`
3. [x] `bot/tests/infrastructure/test_telegram_utils.py` — добавить тесты на `clear_state`
4. [x] `just check-fast` проходит

## Риски и открытые вопросы

- Все 26 call-сайтов проверены: каждый либо сразу ставит новый state, либо не ставит (None — корректное поведение).
- Нет риска регрессии.

## Верификация

`just check-fast` — 345 тестов, все зелёные.
Новые тесты: `test_clear_state_resets_fsm_state`, `test_clear_state_preserves_session_fields`,
`test_clear_state_removes_transient_keys`.
