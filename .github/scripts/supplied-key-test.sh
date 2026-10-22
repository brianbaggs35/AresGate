#!/usr/bin/env bash
# Starts the AresGate container with the app secret key supplied rather than made, the two ways
# a person can supply it: in the environment (ARESGATE_SECRET_KEY in .env), and in a file that
# only root can read, as a Docker secret is (ARESGATE_SECRET_KEY_FILE). Each time it must come up
# healthy without making a key of its own, and keep the key out of its processes' environment.
# Then it supplies a key that is too short, which must stop the container with the reason in the
# log. Uses (and removes) a .env in the current directory, so run it from the repository root
# with the image already built, e.g. in CI after the build.
set -euo pipefail

compose=(docker compose)
workdir="$(mktemp -d)"
trap 'docker compose down --volumes >/dev/null 2>&1 || true; rm -rf .env "$workdir"' EXIT

fail() {
    echo "::error::$1" >&2
    exit 1
}

start() {
    "${compose[@]}" down --volumes >/dev/null 2>&1
    "${compose[@]}" "$@" up --detach --no-build --wait --wait-timeout 180
}

check_supplied_key_is_used() {
    local how="$1" environment
    shift
    ./.github/scripts/smoke-test.sh >/dev/null || fail "the API did not come up with the key supplied $how"
    "${compose[@]}" "$@" exec -T aresgate sh -c 'test ! -e /data/secrets/secret.key' ||
        fail "the container made a key of its own although one was supplied $how"
    # Process 1 is supervisord, which the API, nginx and Postgres inherit their environment from.
    environment="$("${compose[@]}" "$@" exec -T aresgate cat /proc/1/environ | tr '\0' '\n')"
    if grep --quiet '^ARESGATE_SECRET_KEY=' <<<"$environment"; then
        fail "the key supplied $how is still in the environment of the container's processes"
    fi
    echo "A key supplied $how works"
}

key="$(openssl rand -base64 32)"

echo "A key in the environment"
printf 'ARESGATE_SECRET_KEY=%s\n' "$key" >.env
start
check_supplied_key_is_used "in the environment"

echo "A key in a file that only root can read"
(umask 077 && printf '%s\n' "$key" >"$workdir/secret-key.txt")
cat >"$workdir/secret.yml" <<YAML
services:
  aresgate:
    secrets:
      - aresgate_secret_key
secrets:
  aresgate_secret_key:
    file: $workdir/secret-key.txt
YAML
echo 'ARESGATE_SECRET_KEY_FILE=/run/secrets/aresgate_secret_key' >.env
start -f docker-compose.yml -f "$workdir/secret.yml"
check_supplied_key_is_used "in a file" -f docker-compose.yml -f "$workdir/secret.yml"

echo "A key that is too short"
echo 'ARESGATE_SECRET_KEY=too-short' >.env
if start; then
    fail "the container started with a secret key that is too short"
fi
"${compose[@]}" logs --no-color | grep --quiet 'needs at least 32' ||
    fail "the log doesn't say the secret key is too short"
echo "A key that is too short stops the container"
