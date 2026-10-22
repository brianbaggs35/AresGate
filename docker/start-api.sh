#!/bin/sh
# Waits for Postgres, applies migrations, then serves the API on loopback for nginx.
set -eu
cd /app/backend

until pg_isready -q -h /run/postgresql; do sleep 1; done
alembic upgrade head

if [ "${ARESGATE_MODE:-production}" = development ]; then
    exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
fi
exec uvicorn app.main:app --host 127.0.0.1 --port 8000 \
    --workers "${ARESGATE_API_WORKERS:-2}" \
    --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header
