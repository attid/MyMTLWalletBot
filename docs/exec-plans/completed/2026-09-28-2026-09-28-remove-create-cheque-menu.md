# 2026-09-28-remove-create-cheque-menu: Remove /create_cheque from bot command menu

## Context

User wants /create_cheque hidden from the Telegram command menu (keyboard ≡) so it
does not take space (m01134-m01136). Command handler stays functional; only the
BotCommand list entry is removed (user chose option 1 of the proposed variants).
Flow remains reachable via the cheque creation UI (callback CreateCheque →
«Изменить сумму» on the cheque screen).

## Files/Directories To Change

- `bot/start.py` (set_commands, commands_private)
- `bot/tests/other/test_startup_wiring.py` (set_my_commands expectations)

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> m01134: «давай еще команду создать чек уберем из меню, чтоб место там не занимала»
> m01136: «1» (chose: remove /create_cheque from commands_private in set_commands)

## Change Plan

1. [x] `bot/start.py`: remove the /create_cheque BotCommand from commands_private
   in set_commands (bot/start.py:176-179).
2. [x] `bot/tests/other/test_startup_wiring.py`: drop create_cheque from the
   expected command lists at :81 and :91.
3. [x] Run `just check-fast` (lint + test-fast + arch-test).

## Risks / Open Questions

- Risk: none functional — handler @router.message(Command("create_cheque"))
  (bot/routers/cheque.py:95-97) is untouched, command still works if typed
  directly; only the visible menu entry disappears.

## Verification

- `just check-fast` green (lint, test-fast, arch-test).
- test_startup_wiring asserts the new command lists without create_cheque.
