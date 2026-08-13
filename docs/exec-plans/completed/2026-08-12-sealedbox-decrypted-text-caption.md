# sealedbox-decrypted-text-caption: Show short decrypted text in document caption

## Context

Short decrypted text is currently returned only as a document. Users should be
able to read and copy text up to 1000 characters directly from its caption.

## Files/Directories To Change

- `bot/routers/sealedbox.py`
- `bot/infrastructure/utils/telegram_utils.py`
- `bot/infrastructure/workers/sealedbox_worker.py`
- `bot/tests/infrastructure/test_telegram_utils.py`
- `bot/tests/routers/test_sealedbox.py`
- `bot/tests/test_sealedbox_webapp_flow.py`
- `docs/exec-plans/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> User approved the initial paths with `++`, then approved unifying both local
> and WebApp relay delivery: "тогда да делай, все что можно унифицировать надо
> унифицировать".

## Change Plan

1. [x] Add failing tests for short, escaped, long, and binary plaintext.
2. [x] Build one shared monospaced caption formatter for non-empty UTF-8 text
       up to 1000 characters.
3. [x] Attach the shared caption in local and WebApp relay document delivery.
4. [x] Run focused tests and `just check-fast`, then finish the plan.

## Risks / Open Questions

- Telegram uses HTML parse mode, so plaintext must be escaped before wrapping it
  in `<code>` tags.
- The 1000-character limit applies to decoded Unicode text, not byte length.

## Verification

- `uv run pytest bot/tests/routers/test_sealedbox.py -q`
- `just check-fast`
- Expected: short text appears in a monospaced caption; long or binary payloads
  keep the existing document-only response.
