# restore-notification-delivery: Restore legacy notification delivery behind delayed queue

## Context

The delayed Redis queue must control only *when* a blockchain notification is
delivered. Once delivery starts, it must use the complete legacy notification
path, including its keyboard, settings/back callbacks, FSM data interactions,
and `last_message_id` behavior. Remove the separate delivery abstraction that
changed those semantics.

## Files/Directories To Change

- `bot/infrastructure/services/notification_service.py`
- `bot/infrastructure/services/telegram_delivery_service.py`
- `bot/infrastructure/services/notification_coordinator.py`
- `bot/infrastructure/services/app_context.py`
- `bot/start.py`
- `bot/tests/infrastructure/test_notification_webhook.py`
- `bot/tests/infrastructure/test_notification_coordinator.py`
- `bot/tests/infrastructure/test_notification_delivery_worker.py`
- `bot/tests/infrastructure/test_telegram_utils.py`
- `adr/`
- `docs/`

## Edit Permission

- [x] Allowed paths confirmed by user.
- [x] No edits outside listed paths.

Permission evidence (copy user wording or exact confirmation):

> "да возмоно его стоит вообще вырезать чтоб он не путал и отправка была через
> одно место как и было."
>
> "++" confirming the additional wiring/context/test paths required to remove
> the separate delivery service completely.
>
> "++" confirming `bot/tests/infrastructure/test_notification_delivery_worker.py`
> after its protocol import was found during removal.

## Change Plan

1. [x] Add regressions proving queued and immediate delivery both use the full
   legacy notification path and update `last_message_id`/keyboard as before.
2. [x] Remove the separate Telegram notification delivery service and connect
   the coordinator to the legacy notification sender.
3. [x] Preserve Redis hold, durable queue, ordering, retry, worker, and flow
   completion behavior.
4. [x] Correct ADR/architecture documentation to describe delay-only scope.
5. [x] Run focused tests, `just check-fast`, E2E/external checks, and secret scan.

## Risks / Open Questions

- Redis acknowledgement must still occur only after the complete legacy sender
  succeeds.
- Restored `last_message_id` mutation is intentional and explicitly overrides
  ADR-0001's previous UI-isolation decision.

## Verification

- Focused notification webhook/coordinator/worker/Telegram tests: `60 passed`.
- `just check-fast`: passed, including `546 passed`, Ruff, core mypy,
  architecture, docs-contract, and scope-lock checks.
- `just test-e2e-smoke`: `94 passed`.
- `just test-external`: `7 passed`, including real Redis and notifier flow.
- `just secret-scan`: passed; no leaks found.
- Independent Terra final review: `APPROVE`.
