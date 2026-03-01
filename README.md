# MyMTLWalletBot

MyMTLWalletBot

## Development & Quality Control

Use `just` commands from repository root as the standard interface.

```bash
just fmt       # format code
just lint      # ruff + mypy
just test      # full test suite
just test-fast # fast subset for local loop
just test-e2e-smoke # deterministic user-flow smoke tests
just test-external # external/docker integration tests
just arch-test # architectural guardrails
just check     # fmt + lint + test + arch-test
just check-fast # lint + test-fast + arch-test
just metrics   # local code health snapshot
just start-task signing-flow title="Improve signing flow"
just finish-task 2026-03-01-signing-flow.md
just typecheck-full # full mypy sweep (may show legacy debt)
```

### Direct Commands

For manual execution without `just`:

```bash
cd bot

# Ruff
uv run --package mmwb-bot ruff check .
uv run --package mmwb-bot ruff format .

# Mypy
uv run --package mmwb-bot mypy .

# Pytest
uv run --package mmwb-bot pytest tests/
```

See `AI_FIRST.md` and `AGENTS.md` for the AI-first contract and task protocol.
