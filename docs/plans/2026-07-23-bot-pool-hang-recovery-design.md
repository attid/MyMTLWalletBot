# Bot Pool Hang Recovery Design

## Evidence

The production log shows DB connections becoming permanently occupied until the
pool reached `10/10`. At that point the scheduled message worker could no longer
acquire a session. Its `with_timeout(60)` wrapper logged that it was still
waiting but deliberately left the task running. Redis-backed notification work
continued, so the process and event loop were alive.

The log cannot attribute old checkouts to handlers because checkout records
contain only aggregate counts. Historical commit `9518565` also documents why
generic task cancellation is unsafe: Telegram rate-limit retries and bulk
delivery can legitimately take several minutes.

## Design

`DbSessionMiddleware` will not impose a global handler deadline. It will only
bind the Telegram user and update type to DB checkout telemetry. Long handlers
remain compatible with the existing Telegram retry middleware.

`with_timeout` remains a warning-only monitor. It reports elapsed minutes but
does not cancel Telegram work, preserving bulk-delivery behavior.

`cmd_send_message_1m` will snapshot queued-message values in one short session,
perform Telegram and FSM I/O without a session, and use a new short session to
persist each terminal status. This prevents an unavailable external service
from reserving a Firebird connection.

Pool events will retain checkout timestamps and task ownership on the SQLAlchemy
connection record. Slow returns receive a structured warning. The existing
functional health service already performs a bounded real session acquisition
and SQL query, which detects both pool waits and blocked connection creation
without relying on an inaccurate connection-count threshold.

A currently running message worker remains healthy even after the warning
threshold. If it is blocked by Firebird, the independent DB probe fails and the
container becomes unhealthy. A worker that is not running and has not completed
for too long remains a scheduler failure.

## Error Handling and Tests

Worker delivery errors mark an existing queue record failed in a fresh committed
session. Telegram retries may continue for as long as required without holding
a Firebird connection.

Regression tests use blocking coroutines and instrumented fake pools. They prove
that generic timeout monitoring does not cancel its child, worker external I/O
sees zero open sessions, long active delivery remains healthy with a responsive
database, and DB checkouts retain their update owner.
