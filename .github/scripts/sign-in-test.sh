#!/usr/bin/env bash
# Sets up a fresh AresGate container and signs in to it the way the web app does: with the setup
# code from the container's log, over HTTPS through nginx, with the browser's Origin header and
# the session cookie. Then it checks that the sign-in survives a restart, that no new setup code
# is printed once the account exists, that the system endpoint needs a sign-in, that a request's
# ID is in the response and in both nginx's and the API's log, that an authenticator app can be
# added, is asked for when signing in (once for each code), and is turned off by the command for
# someone who has lost it, and that five wrong passwords lock the account. Run it from the repository root against a container that has just started on
# empty data, with the stack up and the ports in the environment, as the smoke test is.

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

# What a sign-in sends: the account's username and, unless another is given, its password.
credentials() {
    local given="${1:-$password}"
    json --arg u "$username" --arg p "$given" '{username: $u, password: $p}'
}

# What the second step sends: the challenge the password earned, and a code.
second_step() {
    local challenge="$1" code="$2"
    json --arg h "$challenge" --arg c "$code" '{challenge: $h, code: $c}'
}

# The security token of the sign-in the last answer started, which changes need.
csrf_token() {
    jq --raw-output '.csrf_token' <<<"$body"
}

# Signs out the sign-in whose token is in $csrf.
sign_out() {
    request POST /api/auth/logout "" --header "X-CSRF-Token: $csrf"
    expect 204 "signing out"
}

# totp SECRET [PERIODS_AHEAD]: the six digits an authenticator app shows for SECRET, worked out
# here and not by the API, so the test doesn't rely on the code it is testing. A code is good once
# and the API accepts the next period's too, so asking for one ahead gives a code that is not the
# one the app was confirmed with.
totp() {
    local secret="$1" periods_ahead="${2:-0}"
    python3 - "$secret" "$periods_ahead" <<'PY'
import base64, hashlib, hmac, struct, sys, time

counter = int(time.time()) // 30 + int(sys.argv[2])
digest = hmac.new(base64.b32decode(sys.argv[1]), struct.pack(">Q", counter), hashlib.sha1).digest()
offset = digest[-1] & 15
number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
print(f"{number % 10**6:06d}")
PY
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
csrf="$(csrf_token)"
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
sign_out
request GET /api/auth/session ""
expect 401 "reading the session after signing out"

echo "Signing in"
request POST /api/auth/login "$(credentials "not the password")"
expect 401 "signing in with a wrong password"
request POST /api/auth/login "$(credentials)"
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

echo "The system endpoint is for someone who is signed in"
request GET /api/system ""
expect 200 "reading the system endpoint"
jq --exit-status '.version != "" and .database.status == "ok" and .uptime_seconds >= 0' <<<"$body" >/dev/null ||
    fail "the system endpoint says: $body"
signed_out="$(curl --silent --insecure --output /dev/null --write-out '%{http_code}' "$origin/api/system")"
[[ "$signed_out" = 401 ]] || fail "the system endpoint answered $signed_out to someone not signed in, not 401"

echo "A request has an ID, which is in the response, in nginx's log and in the API's log"
request_headers="$(curl --silent --insecure --dump-header - --output /dev/null "$origin/api/no-such-page?a=1")"
request_id="$(grep --ignore-case '^x-request-id:' <<<"$request_headers" | tr -d '\r' | awk '{print $2}')"
[[ "$request_id" =~ ^[0-9a-f]{32}$ ]] || fail "the response has no request ID: $request_headers"
sleep 1
logged="$(docker compose logs --no-color aresgate 2>&1 | grep --fixed-strings "$request_id" || true)"
grep --quiet 'GET /api/no-such-page?a=1 HTTP' <<<"$logged" || fail "nginx's log has no line with the request's ID"
api_line="$(grep '"logger": "aresgate.request"' <<<"$logged" || true)"
[[ "$api_line" = *'"path": "/api/no-such-page"'* ]] || fail "the API's log has no line with the request's ID"
[[ "$api_line" != *'a=1'* ]] || fail "the API logged the query string: $api_line"

# The sign-in rate limit allows a burst of 20 requests and then 10 a minute, so this takes only
# the requests it needs.
echo "An authenticator app is added with a code from it"
request GET /api/auth/session ""
expect 200 "reading the session"
csrf="$(csrf_token)"
request POST /api/auth/two-factor/enroll "" --header "X-CSRF-Token: $csrf"
expect 201 "starting to add an authenticator app"
secret="$(jq --raw-output '.secret' <<<"$body")"
jq --exit-status --arg u "$username" '.otpauth_uri | startswith("otpauth://totp/AresGate:" + $u + "?")' <<<"$body" >/dev/null ||
    fail "the QR code's address isn't for this account: $body"
request POST /api/auth/two-factor/confirm "$(json --arg c "$(totp "$secret")" '{code: $c}')" --header "X-CSRF-Token: $csrf"
expect 200 "confirming with the app's code"
jq --exit-status '.recovery_codes | length == 10' <<<"$body" >/dev/null || fail "there aren't ten recovery codes: $body"
mapfile -t recovery_codes < <(jq --raw-output '.recovery_codes[]' <<<"$body")
request GET /api/auth/two-factor ""
jq --exit-status '.enabled == true and .recovery_codes_left == 10' <<<"$body" >/dev/null || fail "the status says: $body"

echo "The password alone no longer signs in; a code from the app finishes it"
sign_out
request POST /api/auth/login "$(credentials)"
expect 200 "signing in with the password"
jq --exit-status '.two_factor_required == true and (.challenge | length) > 0 and has("csrf_token") == false' <<<"$body" >/dev/null ||
    fail "the password alone should only earn a challenge: $body"
challenge="$(jq --raw-output '.challenge' <<<"$body")"
if grep --quiet '__Host-aresgate_session' "$jar"; then
    fail "a session cookie was set before the second step"
fi
request GET /api/auth/session ""
expect 401 "reading the session before the second step"
request POST /api/auth/login/two-factor "$(second_step "$challenge" 000000)"
expect 401 "the second step with a wrong code"
request POST /api/auth/login/two-factor "$(second_step "$challenge" "$(totp "$secret" 1)")"
expect 200 "the second step with the app's code"
request GET /api/auth/session ""
expect 200 "reading the session after the second step"

echo "A recovery code finishes signing in too"
csrf="$(csrf_token)"
sign_out
request POST /api/auth/login "$(credentials)"
challenge="$(jq --raw-output '.challenge' <<<"$body")"
request POST /api/auth/login/two-factor "$(second_step "$challenge" "${recovery_codes[0]}")"
expect 200 "the second step with a recovery code"
request GET /api/auth/two-factor ""
jq --exit-status '.recovery_codes_left == 9' <<<"$body" >/dev/null || fail "a recovery code was used, but the status says: $body"

echo "The command turns it off for someone who has lost the app and the codes, and ends their sign-ins"
make two-factor-off ACCOUNT="$username" >/dev/null
request GET /api/auth/session ""
expect 401 "reading the session after the command"
request POST /api/auth/login "$(credentials)"
expect 200 "signing in with the password alone"
jq --exit-status 'has("csrf_token") and (has("two_factor_required") | not)' <<<"$body" >/dev/null ||
    fail "the password alone should sign in now: $body"
if make two-factor-off ACCOUNT="$username" >/dev/null 2>&1; then
    fail "the command turned off a second step that was already off"
fi

echo "The audit log has the second step, from the web and from the command, and none of its secrets"
request GET "/api/audit/events?action=auth.two_factor_enabled&action=auth.two_factor_failed&action=auth.two_factor_disabled&limit=200" ""
expect 200 "reading the second step's events"
actions="$(jq --raw-output '[.events[].action] | sort | join(" ")' <<<"$body")"
[[ "$actions" = "auth.two_factor_disabled auth.two_factor_enabled auth.two_factor_failed" ]] ||
    fail "the second step's events are: $actions"
jq --exit-status '[.events[] | select(.action == "auth.two_factor_disabled" and .detail.by == "command_line" and .client_address == null and .user_agent == "command line")] | length == 1' \
    <<<"$body" >/dev/null || fail "the command isn't in the audit log as itself: $body"
for hidden in "$secret" "${recovery_codes[@]}"; do
    ! grep --quiet --fixed-strings "$hidden" <<<"$body" || fail "the audit log shows a secret"
done

echo "Five wrong passwords lock the account, even for the right password"
for _ in 1 2 3 4 5; do
    request POST /api/auth/login "$(json --arg u "$username" '{username: $u, password: "guess"}')"
    expect 401 "guessing"
done
request POST /api/auth/login "$(credentials)" \
    --dump-header "$workdir/headers"
expect 429 "signing in while locked"
grep --quiet --ignore-case '^retry-after: [0-9]' "$workdir/headers" || fail "the lockout has no Retry-After"

echo "The audit log says the fifth wrong password locked the account, and not the attempts after it"
request GET "/api/audit/events?action=auth.login_failed&limit=200" ""
expect 200 "reading the failed sign-ins"
jq --exit-status '(.events | length) == 6 and ([.events[] | select(.detail.locked_for_seconds != null)] | length) == 1' \
    <<<"$body" >/dev/null || fail "the failed sign-ins are not as expected: $body"

echo "Setup and sign-in test passed"
