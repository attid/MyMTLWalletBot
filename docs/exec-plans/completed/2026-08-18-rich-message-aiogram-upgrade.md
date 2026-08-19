# rich-message-aiogram-upgrade: Upgrade aiogram and validate Telegram rich messages

## Context

Upgrade the Telegram framework to a release that supports Bot API 10.2 rich
messages, then validate the new API against the configured test bot with two
representative wallet screens.

## Files/Directories To Change

- `bot/pyproject.toml`
- `uv.lock`
- `docs/exec-plans/active/`
- `docs/exec-plans/completed/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++

This confirms the immediately preceding explicit request for permission to
change these dependency and execution-plan paths.

## Change Plan

1. [x] Raise the aiogram minimum version in `bot/pyproject.toml` to 3.30.0.
2. [x] Refresh `uv.lock` for aiogram and its transitive dependency changes.
3. [x] Verify the installed aiogram exposes `InputRichMessage` and
       `Bot.send_rich_message`.
4. [x] Send representative wallet home and decoded-transaction rich messages
       through the configured test bot.
5. [x] Run `just check-fast`.

## Risks / Open Questions

- Dependency changes can affect incoming update parsing and existing bot method
  serialization even when application code is unchanged.
- Telegram client rendering may differ between mobile, desktop, and web; the
  live messages are intended to expose those differences for manual review.

## Verification

- `uv lock --upgrade-package aiogram`
- `uv run pytest bot/tests/other/test_import_sanity.py -q`
- `just check-fast`
- Live `sendRichMessage` responses return `ok=true` for both samples.

Observed results:

- Import sanity: 124 passed.
- Full fast gate: Ruff passed, mypy passed, 421 tests passed, and all
  architecture/documentation guardrails passed.
- Telegram accepted rich message IDs 8951 and 8952; the decoded-transaction
  sample includes a 6232-character raw XDR block.
