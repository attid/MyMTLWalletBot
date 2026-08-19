# telegram-rich-messages-note: Document Telegram rich-message evaluation

## Context

Capture the Telegram Rich Messages investigation and live client findings so
the team can pause the decision and resume it without repeating discovery.

## Files/Directories To Change

- `docs/telegram-rich-messages.md`
- `docs/exec-plans/active/`
- `docs/exec-plans/completed/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> давай про рич сообщения сохраним где-то доку чтоб вернуться к этому через недельку

Markdown documentation required by the task may be added under the repository
documentation exception in `AGENTS.md`.

## Change Plan

1. [x] Record verified Bot API and aiogram capabilities.
2. [x] Record candidate bot screens and implementation boundaries.
3. [x] Record live client observations and the follow-up checklist.
4. [x] Run documentation and execution-plan guardrails.

## Risks / Open Questions

- The document must distinguish verified behavior from proposed product design.
- Desktop and Web rendering observations are still pending.

## Verification

- `uv run python .linters/check_docs_contract.py`
- `uv run python .linters/check_exec_plan_scope_lock.py`
- Both commands exit successfully.

Observed results: both documentation guardrails passed and `git diff --check`
reported no whitespace errors.
