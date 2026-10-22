#!/usr/bin/env bash
# Runs the Playwright tests against AresGate started straight on this machine, with no
# container: the API (with the end-to-end test harness, under coverage) on a Postgres that
# ARESGATE_DATABASE_URL points at, and the built web app served by `vite preview`, which
# proxies /api to it. CI runs this next to the run against the e2e container, so a failure
# that shows up in only one of them points at the container. `make e2e-host` runs it on a
# throwaway Postgres. Extra arguments go to Playwright, e.g. --shard=1/2 or home.
set -euo pipefail

: "${ARESGATE_DATABASE_URL:?Set ARESGATE_DATABASE_URL to a Postgres database the tests may erase}"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
api_port="${ARESGATE_E2E_API_PORT:-18000}"
web_port="${ARESGATE_E2E_HOST_PORT:-14173}"
pids=()

cleanup() {
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT

fail() {
    echo "::error::$1" >&2
    exit 1
}

cd "$root/backend"
# The harness refuses to start unless the API is told it's a test server.
export ARESGATE_ENVIRONMENT=test
# The API won't start without an app secret key. These tests keep nothing worth protecting, so
# a throwaway one will do.
ARESGATE_SECRET_KEY="${ARESGATE_SECRET_KEY:-$(openssl rand -base64 32)}"
export ARESGATE_SECRET_KEY
echo "Migrating the database"
uv run --no-sync --no-build alembic upgrade head

echo "Starting the API on port $api_port, measured by coverage"
uv run --no-sync --no-build python -m coverage run --rcfile="$root/docker/e2e/coveragerc" \
    -m uvicorn e2e.main:create_e2e_app --factory --host 127.0.0.1 --port "$api_port" &
pids+=("$!")

cd "$root/frontend"
echo "Building the web app, with source maps for coverage"
npm run build:e2e

echo "Serving the web app on port $web_port"
ARESGATE_API_URL="http://127.0.0.1:$api_port" \
    ./node_modules/.bin/vite preview --host 127.0.0.1 --port "$web_port" --strictPort &
pids+=("$!")

# Through the web app's proxy, so both servers are up.
for _ in $(seq 60); do
    curl --silent --fail --output /dev/null "http://127.0.0.1:$web_port/api/health" && break
    sleep 1
done
curl --silent --fail --output /dev/null "http://127.0.0.1:$web_port/api/health" ||
    fail "the API and web app did not come up"

ARESGATE_E2E_URL="http://127.0.0.1:$web_port" npm run e2e -- "$@"
