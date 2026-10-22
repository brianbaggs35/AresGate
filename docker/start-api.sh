#!/bin/sh
# Checks the app secret key, waits for Postgres, applies migrations, prints the setup code if
# nobody has set AresGate up yet, then serves the API on loopback for nginx. The API logs each
# request itself (with an ID that nginx's log shares), so uvicorn's own access log is off.
set -eu
cd /app/backend

# Stops here, with the reason in the log, if the key is missing or too short.
python -c 'from app.secret_key import check_or_exit; check_or_exit()'
until pg_isready -q -h /run/postgresql; do sleep 1; done
alembic upgrade head
# A new code each time the container starts, until the account exists.
python -c 'from app.security.setup_code import announce; announce()'

if [ "${ARESGATE_MODE:-production}" = development ]; then
    exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log --reload --reload-dir app
fi
exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log \
    --workers "${ARESGATE_API_WORKERS:-2}" \
    --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header
