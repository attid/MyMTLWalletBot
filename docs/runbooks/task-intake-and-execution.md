# Task Intake And Execution

## Goal

Ensure every non-trivial task starts in AI-first workflow mode.

## Steps

1. Identify target files/directories for the task.
2. Confirm allowed edit paths.
3. Create execution plan:

   ```bash
   just start-task <task-id> title="<short title>"
   ```

4. Fill checkboxes in the created plan under `docs/exec-plans/active/`.
5. Implement with minimal diff.
6. Run validation commands:

   ```bash
   just arch-test
   just lint
   just test-fast
   ```

7. Move completed plan:

   ```bash
   just finish-task <plan-file>
   ```

## Notes

- Use `just typecheck-full` for full mypy debt visibility when needed.
- If checks fail repeatedly, use `docs/runbooks/ci-failure-triage.md`.
