#!/usr/bin/env bash
# Checks that what a person saves in AresGate is still there after stopping and starting it, in
# every way they can: make stop and make start (the container is kept), make restart, and make
# down and then up (the container is made again from the image, on the same data volume). It
# sets up an account on empty data, saves an integration and an AI provider, each with a secret,
# and after each way looks for the same things: the account still signs in, the settings are
# still in the API, the sealed secrets in the database are the very same bytes, the app secret key
# is the same file, and make data names the volume. The sealed secrets and the key being the same
# is what shows the secrets still open, without a call to the integration or the provider.
# Run it from the repository root with the image built and the ports in the environment, as the
# other container tests are. It removes the stack's data when it starts and when it ends.
# The jq programs name their own variables ($key), which the shell must not expand.
# shellcheck disable=SC2016
set -euo pipefail

https_port="${ARESGATE_HTTPS_PORT:-443}"
# The origin a browser sends: no port when it's the default one.
origin="https://localhost"
[[ "$https_port" = 443 ]] || origin="$origin:$https_port"
username="ci-admin"
password="an ordinary sentence for the test"
integration_url="https://192.168.50.10:8080"
integration_secret="an-integration-secret-that-is-saved-for-the-test"
provider_secret="a-provider-secret-that-is-saved-for-the-test"
workdir="$(mktemp -d)"
jar="$workdir/cookies.txt"
trap 'docker compose down --volumes >/dev/null 2>&1 || true; rm -rf "$workdir"' EXIT

status=""
body=""

fail() {
    echo "::error::$1" >&2
    exit 1
}

# request METHOD PATH JSON: the answer's status code and body are left in $status and $body, and
# the cookies are kept between requests as a browser would.
request() {
    local method="$1" path="$2" data="$3"
    shift 3
    local args=(--silent --show-error --insecure --request "$method" --header "Origin: $origin"
        --cookie "$jar" --cookie-jar "$jar" --output "$workdir/body" --write-out '%{http_code}')
    if [[ -n "$data" ]]; then
        args+=(--header 'Content-Type: application/json' --data "$data")
    fi
    status="$(curl "${args[@]}" "$@" "$origin$path")"
    body="$(<"$workdir/body")"
}

expect() {
    local wanted="$1" what="$2"
    [[ "$status" = "$wanted" ]] || fail "$what: expected $wanted, got $status ($body)"
}

json() {
    jq --null-input --compact-output "$@"
}

# Waits until the container says it is healthy, which `docker compose start` and `restart` don't.
wait_healthy() {
    local what="$1" waited=0 health=""
    until [[ "$health" = healthy ]]; do
        ((waited < 180)) || fail "$what: the container was not healthy 180 seconds after it started (it is '$health')"
        sleep 2
        waited=$((waited + 2))
        health="$(docker inspect --format '{{.State.Health.Status}}' aresgate 2>/dev/null || true)"
    done
}

# What is in the database that has to stay exactly as it is: every sealed secret, with what it is
# for.
sealed_secrets() {
    docker compose exec -T -u aresgate aresgate psql -h /run/postgresql aresgate --no-psqlrc --tuples-only --no-align \
        --command 'SELECT kind, name, field, value_sealed FROM credentials ORDER BY kind, name, field'
}

app_secret_key() {
    docker compose exec -T -u aresgate aresgate sha256sum /data/secrets/secret.key
}

echo "AresGate starts on empty data and is set up"
docker compose down --volumes >/dev/null 2>&1
docker compose up --detach --no-build --wait --wait-timeout 180
logs="$(docker compose logs --no-color aresgate 2>&1)"
grep --quiet --fixed-strings 'making a new database' <<<"$logs" || fail "the first start did not say it made a new database"
code="$(grep --after-context=3 'enter this setup code' <<<"$logs" |
    grep --only-matching --extended-regexp '[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}' | tail -n 1)"
[[ -n "$code" ]] || fail "the container's log doesn't show a setup code"
request POST /api/setup "$(json --arg c "$code" --arg u "$username" --arg p "$password" '{code: $c, username: $u, password: $p}')"
expect 201 "setting up"
csrf="$(jq --raw-output '.csrf_token' <<<"$body")"

echo "An integration and an AI provider are saved, each with a secret"
request PUT /api/integrations/crowdsec "$(json --arg url "$integration_url" --arg key "$integration_secret" \
    '{connections: {lapi: {url: $url, secrets: {api_key: $key}}}}')" --header "X-CSRF-Token: $csrf"
expect 200 "saving the CrowdSec integration"
request PUT /api/ai/providers/anthropic "$(json --arg key "$provider_secret" '{model: "claude-haiku-5-5", api_key: $key}')" \
    --header "X-CSRF-Token: $csrf"
expect 200 "saving the Anthropic provider"
request PUT /api/ai/use "$(json '{enabled: true, provider: "anthropic", redaction: "strict"}')" --header "X-CSRF-Token: $csrf"
expect 200 "choosing the Anthropic provider"

sealed_before="$(sealed_secrets)"
[[ "$(wc -l <<<"$sealed_before")" -eq 2 ]] || fail "expected two sealed secrets in the database, found: $sealed_before"
! grep --quiet --fixed-strings -e "$integration_secret" -e "$provider_secret" <<<"$sealed_before" || fail "a secret is in the database as it was typed"
key_before="$(app_secret_key)"

# check_kept WHAT: signs in again, and looks for everything the settings are made of.
check_kept() {
    local what="$1" sealed
    wait_healthy "$what"
    : >"$jar"
    request POST /api/auth/login "$(json --arg u "$username" --arg p "$password" '{username: $u, password: $p}')"
    expect 200 "$what: signing in with the account made before"

    request GET /api/integrations/crowdsec ""
    expect 200 "$what: reading the integration"
    jq --exit-status --arg url "$integration_url" \
        '.connections[] | select(.definition.key == "lapi") | .url == $url and .secrets_set == ["api_key"]' \
        <<<"$body" >/dev/null || fail "$what: the integration lost its address or its secret: $body"

    request GET /api/ai ""
    expect 200 "$what: reading the AI settings"
    jq --exit-status '.enabled == true and .provider == "anthropic"' <<<"$body" >/dev/null ||
        fail "$what: AI is no longer on with the Anthropic provider: $body"
    jq --exit-status '.providers[] | select(.key == "anthropic") | .configured and .key_saved and .model == "claude-haiku-5-5"' \
        <<<"$body" >/dev/null || fail "$what: the Anthropic provider lost its model or its key: $body"

    sealed="$(sealed_secrets)"
    [[ "$sealed" = "$sealed_before" ]] || fail "$what: the sealed secrets in the database changed"
    [[ "$(app_secret_key)" = "$key_before" ]] || fail "$what: the app secret key changed"
    echo "  $what: the account, the integration, the AI provider, the sealed secrets and the key are as they were"
}

# check_data_names_the_volume USED: make data names the volume, and says whether a container uses it.
check_data_names_the_volume() {
    local used="$1" shown
    shown="$(make --no-print-directory data 2>&1)" || fail "make data failed: $shown"
    grep --quiet --fixed-strings 'Data volume aresgate_aresgate-data' <<<"$shown" || fail "make data didn't name the volume: $shown"
    if [[ "$used" = yes ]]; then
        grep --quiet --fixed-strings 'used by aresgate' <<<"$shown" || fail "make data didn't say the container uses the volume: $shown"
    else
        grep --quiet --fixed-strings 'nothing uses it now' <<<"$shown" || fail "make data didn't warn that nothing uses the volume: $shown"
    fi
}

echo "make stop keeps the container, and make start brings it back"
check_data_names_the_volume yes
make --no-print-directory stop >/dev/null
[[ -n "$(docker compose ps --all --quiet)" ]] || fail "make stop removed the container"
[[ -z "$(docker compose ps --quiet)" ]] || fail "make stop left the container running"
check_data_names_the_volume yes
make --no-print-directory start >/dev/null
check_kept "make stop and make start"

echo "make restart"
make --no-print-directory restart >/dev/null
check_kept "make restart"

echo "make down removes the container and keeps the data, and starting again finds it"
make --no-print-directory down >/dev/null
[[ -z "$(docker compose ps --all --quiet)" ]] || fail "make down left a container"
check_data_names_the_volume no
if make --no-print-directory start >/dev/null 2>&1; then
    fail "make start started something although make down had removed the container"
fi
docker compose up --detach --no-build --wait --wait-timeout 180
logs="$(docker compose logs --no-color aresgate 2>&1)"
grep --quiet --fixed-strings 'using the database already in the data volume' <<<"$logs" || fail "the start after make down didn't say it used the database already there"
! grep --quiet --fixed-strings 'making a new database' <<<"$logs" || fail "the start after make down made a new database"
check_kept "make down and up"

echo "Stopping and starting AresGate keeps what was saved"
