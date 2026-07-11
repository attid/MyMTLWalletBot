# Glossary

## Core Terms

- **AI-first workflow**: Development process where agents can execute tasks
  autonomously under strict, machine-checkable rules.
- **Execution plan**: Versioned task plan under `docs/exec-plans/` used for
  non-trivial work.
- **Guardrail**: Automated check that enforces architecture or quality rules.
- **Boundary**: Allowed dependency direction between modules/layers.
- **Router test**: Integration-style test for aiogram handlers in
  `bot/tests/routers/`; must include `mock_telegram`.

## Bot Domain Terms

- **App context**: Dependency container injected into handlers/tests.
- **Use case**: Orchestration logic in `bot/core/use_cases/`.
- **Repository factory**: Factory providing repository instances bound to a DB
  session.
- **Commit discipline**: Mandatory explicit `await session.commit()` for writes.
- **Blockchain notification**: A wallet event confirmed by the blockchain;
  user-flow screens such as “transaction sent” are not notifications.
- **Notification hold**: Absolute Redis timestamp until which background
  blockchain notifications are queued while the user remains active.
- **Pending notification queue**: Durable ordered Redis queue independent from
  FSM state and safe across process restarts.
- **Notification badge**: Derived inline-keyboard row showing the pending count;
  it does not navigate, replace the UI screen, or change FSM state.
- **Notification flush**: Token-locked ordered delivery of a user's pending
  queue, either after inactivity, at flow completion, or by explicit badge click.
