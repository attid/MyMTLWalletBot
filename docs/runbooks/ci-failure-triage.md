# CI Failure Triage

## Goal

Resolve CI failures quickly with deterministic steps.

## Checklist

1. Reproduce locally with `just check`.
2. If formatter changed files, re-run checks and commit formatting changes.
3. Fix lint/type violations from `just lint`.
4. Fix failing tests from `just test`.
5. Fix architecture/doc contract failures from `just arch-test`.

## Common Cases

- **Ruff format diff**: run `just fmt`, then verify clean diff and rerun checks.
- **Mypy errors**: add missing types or narrow dynamic behavior with typed
  adapters.
- **Router test failures**: verify `mock_telegram` fixture usage and DI wiring.
- **Boundary violations**: move imports behind interfaces or adjust module
  ownership.

## Escalation

Escalate when all apply:

- issue persists after two focused attempts,
- root cause is outside current task scope, or
- fix requires architecture choice not covered in docs.

When escalating, include:

- what failed,
- what was tried,
- proposed options and tradeoffs.
