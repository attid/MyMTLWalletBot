# sealedbox-document-ui: Route sealed-box documents through tracked UI delivery

## Context

The WebApp relay worker sends its result with `bot.send_document()` directly.
That bypasses tracked Telegram UI delivery, so the document's Home button is
immediately rejected as old because `last_message_id` still points elsewhere.

## Files/Directories To Change

- `bot/infrastructure/utils/telegram_utils.py`
- `bot/routers/sealedbox.py`
- `bot/infrastructure/workers/sealedbox_worker.py`
- `bot/tests/infrastructure/test_telegram_utils.py`
- `bot/tests/routers/test_sealedbox.py`
- `bot/tests/test_sealedbox_webapp_flow.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User approved the listed paths with `++`.

## Change Plan

1. [x] Add failing tests requiring document delivery to track its message ID.
2. [x] Add a shared document UI sender with notification badge coordination.
3. [x] Route normal and relayed sealed-box documents through the shared sender.
4. [x] Preserve the resulting `last_message_id` when completing the flow.
5. [x] Run focused tests and `just check-fast`, then finish the plan.

## Risks / Open Questions

- Pending notification flushes may replace the result screen after flow
  completion; the shared sender must establish correct state before releasing
  the notification hold.

## Verification

- `uv run pytest bot/tests/infrastructure/test_telegram_utils.py bot/tests/routers/test_sealedbox.py bot/tests/test_sealedbox_webapp_flow.py -q`
- `just check-fast`
- Expected: document IDs are tracked and Home callbacks are no longer stale.
