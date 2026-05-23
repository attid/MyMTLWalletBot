# signing-facade: Add signing facade for anchor flows

## Context

We are preparing SEP-6/SEP-24 anchor flows. Current signing behavior is
implemented mostly through `routers.sign` and implicit FSM keys (`xdr`,
`operation`, `success_msg`, `fsm_after_send`). New anchor-transfer code should
depend on an explicit signing facade instead of coupling directly to router FSM
details.

## Files/Directories To Change

- `bot/infrastructure/services/signing_facade.py`
- `bot/tests/infrastructure/test_signing_facade.py`
- `bot/routers/sign.py`
- `docs/exec-plans/active/2026-05-23-signing-facade.md`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> +

## Change Plan

1. [x] Add a failing test for a signing facade request that stores the expected
   FSM contract and invokes the existing PIN/WebApp prompt path.
2. [x] Add typed request/result/purpose/mode objects and minimal facade
   implementation in `bot/infrastructure/services/signing_facade.py`.
3. [x] Keep `routers.sign` integration minimal; only add a small wrapper if the
   facade needs a stable callable entrypoint.
4. [x] Run focused tests for the new facade.
5. [x] Run relevant lint/tests (`just check-fast` if feasible).

## Risks / Open Questions

- Risk: changing the legacy signing path can regress many existing flows.
  Mitigation: keep the first increment as a facade over existing behavior.
- Open question: whether future SEP flows should use callbacks, workflow IDs,
  or DB transfer IDs. This increment supports correlation metadata but does not
  implement SEP transfer persistence.

## Verification

- `uv run pytest bot/tests/infrastructure/test_signing_facade.py -q`
  - Passed: `2 passed in 0.54s`.
- `just check-fast`
  - Passed: ruff, mypy core, `392 passed`, import boundaries, docs contract,
    and exec-plan scope lock.
