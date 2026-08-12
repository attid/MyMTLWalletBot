# router-test-session-close: Skip Aiogram SSL wait for local HTTP tests

## Context

Aiogram 3.24 adds an unconditional 250 ms SSL graceful-shutdown sleep in
`AiohttpSession.close()`. Router tests use a function-scoped bot against a
local plain-HTTP Telegram server, so this sleep consumed exactly 50.00 seconds
of a 66.97-second router suite. A diagnostic run that closed the underlying
aiohttp session directly completed the same 225 tests in 17.00 seconds.

## Files/Directories To Change

- `bot/tests/conftest.py`
- `docs/exec-plans/active/2026-08-12-router-test-session-close.md`
- `docs/exec-plans/completed/2026-08-12-router-test-session-close.md`
- `docs/plans/2026-08-12-router-test-session-close.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> After the assistant named `bot/tests/conftest.py` and Markdown execution-plan
> files, the user replied `++`.

## Change Plan

1. [x] Establish RED baseline and isolate Aiogram's 250 ms close sleep.
2. [x] Retain the local aiohttp client session and close it directly in the
       `router_bot` fixture.
3. [x] Run the complete router suite and compare timing with the baseline.
4. [x] Run repository verification gates.
5. [x] Move the completed plan to `docs/exec-plans/completed/`.

## Risks / Open Questions

- Production sessions must continue using Aiogram's normal SSL shutdown path.
- The optimization is limited to the plain-HTTP test fixture.
- The direct aiohttp session handle must still be closed on fixture teardown.

## Verification

- `uv run --package mmwb-bot pytest tests/routers -q --durations=0`
- `just check-fast`
- `just test`
- `git diff --check`
- Router suite: 225 passed in 19.25 seconds, down from 66.97 seconds.
- `just check-fast`: passed (589 tests plus lint, mypy, and architecture checks).
- `just test`: passed (900 passed, 7 deselected in 32.16 seconds).
- Three router modules with their own legacy `bot` fixtures still account for
  isolated 0.25-second teardowns; they are outside the approved edit scope.
- No production code changed.
