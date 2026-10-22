#!/bin/sh
# The e2e image's API: migrations as in production, then the API with the end-to-end test
# harness mounted, measured by coverage in one worker so every request is counted.
set -eu
cd /app/backend

until pg_isready -q -h /run/postgresql; do sleep 1; done
alembic upgrade head

exec python -m coverage run --rcfile=/app/docker/e2e/coveragerc \
    -m uvicorn e2e.main:create_e2e_app --factory --host 127.0.0.1 --port 8000 \
    --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header
