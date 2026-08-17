# fix-receive-qr-memory: Send receive QR code from memory

## Context

The `Receive` callback writes a QR code to `qr/<address>.png`, but the ignored
runtime directory is absent from clean container builds. Generate and upload the
PNG in memory so delivery does not depend on mutable container storage.

## Files/Directories To Change

- `bot/routers/receive.py`
- `bot/routers/start_msg.py`
- `bot/tests/routers/test_receive.py`
- `docs/exec-plans/active/2026-08-17-fix-receive-qr-memory.md`
- `docs/exec-plans/completed/2026-08-17-fix-receive-qr-memory.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> ++
>
> ++ (expanded permission for `bot/routers/start_msg.py`)

## Change Plan

1. [x] Add a regression test proving `Receive` works without a `qr` directory.
2. [x] Generate the PNG into memory and upload it with `BufferedInputFile`.
3. [x] Keep the QR image helper covered without filesystem output.
4. [x] Confirm no public contract or architecture documentation changes are needed.
5. [x] Run focused tests and `just check-fast`.

## Risks / Open Questions

- Telegram multipart upload must receive valid PNG bytes and a stable filename.
- No open product or architecture questions.

## Verification

- `uv run pytest bot/tests/routers/test_receive.py`
- `just check-fast`
- Expected: Receive router tests pass without creating `qr/`; all fast gates pass.
