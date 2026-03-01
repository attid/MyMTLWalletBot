# ai-first-workflow-hardening: Harden AI-first workflow bootstrap

## Context

Align daily development with AI-first contract so every non-trivial task starts
from an execution plan and is validated by mechanical checks.

## Change Plan

1. [x] Add task lifecycle commands (`start-task` and `finish-task`) in
   `justfile` and helper scripts in `.linters/`.
2. [x] Update operator documentation (`AGENTS.md`, `README.md`, runbooks).
3. [x] Stabilize lint gate for immediate use (`ruff` clean + scoped mypy gate).
4. [x] Validate workflow commands and quality gates.
5. [x] Run CI-safe gate (`just check-fast`) and local validations.

## Risks / Open Questions

- Running `just fmt` currently reformats a broad legacy surface in `bot/`, which
  creates a large unrelated diff.
- Team decision needed on when to perform one-time repository-wide formatting.

## Verification

- `just lint` -> pass.
- `just arch-test` -> pass.
- `just test-fast` -> pass.
- `just --list` -> includes `start-task`, `finish-task`, and `check-fast`.
