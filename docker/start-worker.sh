#!/bin/sh
# Checks the app secret key, waits for Postgres and for the API to finish applying migrations
# (the worker reads and writes tables the newest migration makes), then runs the collector
# worker: the process that reads from the integrations on a schedule.
set -eu
cd /app/backend

python -c 'from app.secret_key import check_or_exit; check_or_exit()'
until pg_isready -q -h /run/postgresql && alembic current 2>/dev/null | grep -q '(head)'; do
    sleep 2
done
exec python -m app.worker
