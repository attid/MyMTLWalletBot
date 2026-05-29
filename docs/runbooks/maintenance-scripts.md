# Maintenance Scripts

## Goal

Run one-off maintenance scripts safely in local checkouts and deployed Docker
containers.

## Docker Image Command Pattern

In the bot Docker image, run scripts from `/app/bot` with `python`, not `uv run`:

```bash
cd /app/bot
python scripts/maintenance/backfill_default_xlm_notification_filters.py
```

Do not use `uv run --package ...` inside the image. `/app/bot` is not the uv
workspace root there, so workspace dependencies such as `mmwb-shared` cannot be
resolved from `tool.uv.sources`.

If `uv run` accidentally creates a local virtualenv inside the container, remove
it:

```bash
rm -rf /app/bot/.venv
```

## Default XLM Notification Filter Backfill

Expected first successful run:

```text
Default XLM notification filters created: <positive count>
```

Run the script a second time as an idempotency check. Expected result:

```text
Default XLM notification filters created: 0
```

Firebird may print a late `Connection.__del__` shutdown warning after the
success log when the process exits. Treat the created counter and the second
idempotency run as the source of truth.
