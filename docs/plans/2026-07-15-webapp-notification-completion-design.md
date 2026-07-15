# WebApp Notification Completion Design

## Problem and decision

Local PIN/password signing submits a transaction and then calls the shared
notification completion hook. WebApp signing submits asynchronously in
`signing_worker`; its normal swap/send branch reports success and clears FSM
state without releasing the notification hold. Consequently the notifier
queues the just-submitted transaction and decorates the success keyboard with
a pending badge.

The WebApp worker will mirror the local signing terminal boundary. After a
successful Stellar submit and after an optional `fsm_after_send` callback, it
will call `complete_notification_flow(app_context, user_id)`. The helper is
best-effort and safe when the coordinator is absent. The call stays inside the
successful normal-submit branch.

No completion is added to failed submissions or WebApp sign-only branches:
SEP-10 continues its authentication callback, and tools/callback URL/wallet
connect continue waiting for their explicit send action.

## Regression coverage

A worker test will use fake Redis and the current AppContext injection path,
submit a successful WebApp transaction, and record the ordering of an
`fsm_after_send` callback and coordinator completion. It must observe
`fsm_after_send` before `complete_flow`. A failure case will prove completion
is not called when Stellar submission reports failure.
