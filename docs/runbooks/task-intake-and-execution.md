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

4. Record allowed paths and permission evidence in the plan (`Files/Directories To
   Change` and `Edit Permission` sections).
5. Mark permission checkboxes as done before first edit.
6. Implement with minimal diff.
7. Run validation commands:

   ```bash
   just arch-test
   just lint
   just test-fast
   ```

8. Move completed plan:

   ```bash
   just finish-task <plan-file>
   ```

## Notes

- Use `just typecheck-full` for full mypy debt visibility when needed.
- If checks fail repeatedly, use `docs/runbooks/ci-failure-triage.md`.
