# sealedbox-send-recipient-ux: Align sealed-box recipient flow with send

## Context

The sealed-box encryption flow renders every address-book entry as a separate
button and leaves user-supplied sensitive messages in the chat. Align recipient
selection with the existing `/send` inline chooser and remove every inbound
message handled by the sealed-box flow.

## Files/Directories To Change

- `bot/routers/sealedbox.py`
- `bot/middleware/notification_activity.py`
- `bot/tests/routers/test_sealedbox.py`
- `bot/tests/middleware/test_notification_activity.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "++" after the listed paths, followed by the clarification that all user
> messages and files in the flow must be deleted.

## Change Plan

1. [x] Add failing router regressions for the `/send`-style chooser and deletion
   of every supported/unsupported inbound message.
2. [x] Replace per-entry recipient buttons with the inline address-book chooser
   and remove the obsolete callback route/activity prefix.
3. [x] Delete inbound sealed-box messages before processing every state path.
4. [x] Run focused tests and the repository verification gate.

## Risks / Open Questions

- Telegram may reject deletion of an already removed message; this must not
  prevent encryption/decryption processing and should remain observable.
- File identifiers must remain downloadable after deleting the containing
  Telegram message.

## Verification

- `uv run pytest bot/tests/routers/test_sealedbox.py bot/tests/middleware/test_notification_activity.py`
- `just check-fast`
- All commands pass with no sealed-box callback/address-book regressions.
