#!/usr/bin/env bash
# Sets up a fresh AresGate container and signs in to it the way the web app does: with the setup
# code from the container's log, over HTTPS through nginx, with the browser's Origin header and
# the session cookie. Then it checks that the sign-in survives a restart, that no new setup code
# is printed once the account exists, and that five wrong passwords lock the account. Run it
# from the repository root against a container that has just started on empty data, with the
# stack up and the ports in the environment, as the smoke test is.

# The jq programs name their own variables ($u), which the shell must not expand.
# shellcheck disable=SC2016
set -euo pipefail

https_port="${ARESGATE_HTTPS_PORT:-443}"
# The origin a browser sends: no port when it's the default one.
origin="https://localhost"
[[ "$https_port" = 443 ]] || origin="$origin:$https_port"
username="ci-admin"
password="an ordinary sentence for the test"
workdir="$(mktemp -d)"
jar="$workdir/cookies.txt"
trap 'rm -rf "$workdir"' EXIT

status=""
body=""

fail() {
    echo "::error::$1" >&2
    exit 1
}

# request METHOD PATH JSON [curl options]: the answer's status code and body are left in
# $status and $body, and the cookies are kept between requests as a browser would.
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

echo "A fresh install asks to be set up"
request GET /api/setup/status ""
expect 200 "reading the setup status"
jq --exit-status '.setup_required == true' <<<"$body" >/dev/null || fail "setup is not required: $body"

echo "The log shows a setup code"
logs="$(docker compose logs --no-color aresgate 2>&1)"
code="$(grep --after-context=3 'enter this setup code' <<<"$logs" |
    grep --only-matching --extended-regexp '[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}' | tail -n 1)"
[[ -n "$code" ]] || fail "the container's log doesn't show a setup code"

echo "A change that doesn't say where it came from is refused"
anonymous="$(curl --silent --insecure --output /dev/null --write-out '%{http_code}' --request POST \
    --header 'Content-Type: application/json' --data "$(json '{code: "x", username: "x", password: "x"}')" \
    "$origin/api/setup")"
[[ "$anonymous" = 403 ]] || fail "a change without an Origin was answered $anonymous, not 403"

echo "A wrong setup code is refused"
request POST /api/setup "$(json --arg u "$username" --arg p "$password" '{code: "AAAA-AAAA-AAAA", username: $u, password: $p}')"
expect 403 "setting up with a wrong code"

echo "A weak password is refused, and the code still works"
request POST /api/setup "$(json --arg c "$code" --arg u "$username" '{code: $c, username: $u, password: "short"}')"
expect 422 "setting up with a weak password"

echo "The right code sets up the account and signs in"
request POST /api/setup "$(json --arg c "$code" --arg u "$username" --arg p "$password" '{code: $c, username: $u, password: $p}')"
expect 201 "setting up"
csrf="$(jq --raw-output '.csrf_token' <<<"$body")"
grep --quiet '__Host-aresgate_session' "$jar" || fail "no session cookie was set"
request GET /api/setup/status ""
jq --exit-status '.setup_required == false' <<<"$body" >/dev/null || fail "setup is still required"
request GET /api/auth/session ""
expect 200 "reading the session"
jq --exit-status --arg u "$username" '.username == $u' <<<"$body" >/dev/null || fail "wrong user: $body"

echo "The code works only once"
request POST /api/setup "$(json --arg c "$code" --arg u "intruder" --arg p "$password" '{code: $c, username: $u, password: $p}')"
expect 409 "setting up a second time"

echo "Signing out needs the security token"
request POST /api/auth/logout ""
expect 403 "signing out without the token"
request POST /api/auth/logout "" --header "X-CSRF-Token: $csrf"
expect 204 "signing out"
request GET /api/auth/session ""
expect 401 "reading the session after signing out"

echo "Signing in"
request POST /api/auth/login "$(json --arg u "$username" --arg p "not the password" '{username: $u, password: $p}')"
expect 401 "signing in with a wrong password"
request POST /api/auth/login "$(json --arg u "$username" --arg p "$password" '{username: $u, password: $p}')"
expect 200 "signing in"

echo "A restart keeps the account and the sign-in, and prints no new setup code"
before="$(grep --count 'enter this setup code' <<<"$logs" || true)"
docker compose restart aresgate >/dev/null
docker compose up --detach --no-build --wait --wait-timeout 180
logs="$(docker compose logs --no-color aresgate 2>&1)"
after="$(grep --count 'enter this setup code' <<<"$logs" || true)"
[[ "$after" = "$before" ]] || fail "the restart printed a setup code although the account exists"
request GET /api/setup/status ""
jq --exit-status '.setup_required == false' <<<"$body" >/dev/null || fail "setup is required again"
request GET /api/auth/session ""
expect 200 "reading the session after a restart"

echo "The audit log shows what happened so far, and has kept it through the restart"
request GET "/api/audit/events?limit=200" ""
expect 200 "reading the audit log"
actions="$(jq --raw-output '[.events[].action] | sort | join(" ")' <<<"$body")"
[[ "$actions" = "auth.login_failed auth.login_succeeded auth.logout setup.code_rejected setup.completed" ]] ||
    fail "the audit log holds: $actions"
jq --exit-status --arg u "$username" \
    '[.events[] | select(.action == "setup.completed" and .username == $u and .client_address != null and .user_agent != null)] | length == 1' \
    <<<"$body" >/dev/null || fail "the setup isn't in the audit log with who and from where: $body"
# Neither the setup code nor either password may end up in the log.
for secret in "$code" "AAAA-AAAA-AAAA" "$password" "not the password"; do
    ! grep --quiet --fixed-strings "$secret" <<<"$body" || fail "the audit log shows a secret"
done

echo "Five wrong passwords lock the account, even for the right password"
for _ in 1 2 3 4 5; do
    request POST /api/auth/login "$(json --arg u "$username" '{username: $u, password: "guess"}')"
    expect 401 "guessing"
done
request POST /api/auth/login "$(json --arg u "$username" --arg p "$password" '{username: $u, password: $p}')" \
    --dump-header "$workdir/headers"
expect 429 "signing in while locked"
grep --quiet --ignore-case '^retry-after: [0-9]' "$workdir/headers" || fail "the lockout has no Retry-After"

echo "The audit log says the fifth wrong password locked the account, and not the attempts after it"
request GET "/api/audit/events?action=auth.login_failed&limit=200" ""
expect 200 "reading the failed sign-ins"
jq --exit-status '(.events | length) == 6 and ([.events[] | select(.detail.locked_for_seconds != null)] | length) == 1' \
    <<<"$body" >/dev/null || fail "the failed sign-ins are not as expected: $body"

echo "Setup and sign-in test passed"
