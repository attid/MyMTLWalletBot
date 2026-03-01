# formatting-baseline: Apply full formatting baseline

## Context

Снять блокер массового форматирования, чтобы `just check` проходил без
отката диффа и новые задачи могли работать в полном AI-first цикле.

## Change Plan

1. [x] Запустить `just check` и принять форматирующий дифф.
2. [x] Убедиться, что `ruff`, `mypy core`, `pytest tests/` и `arch-test` зеленые.
3. [x] Повторно прогнать CI-safe гейт `just check-fast`.
4. [x] Зафиксировать результат как новый baseline.
5. [x] Перенести план в completed.

## Risks / Open Questions

- Дифф большой (форматирование), нужно держать отдельно от функциональных правок.

## Verification

- `just check` -> pass.
- `just check-fast` -> pass.
