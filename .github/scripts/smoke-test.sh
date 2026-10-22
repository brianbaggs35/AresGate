#!/usr/bin/env bash
# Smoke test for a running AresGate container: TLS 1.3, the API and database, the web app, the
# HTTP redirect and the security headers. The certificate is self-signed in CI.
set -euo pipefail

https_port="${ARESGATE_HTTPS_PORT:-443}"
http_port="${ARESGATE_HTTP_PORT:-80}"
base="https://localhost:${https_port}"

fail() {
    echo "::error::$1" >&2
    exit 1
}

echo "API health"
health="$(curl --silent --show-error --fail --insecure "$base/api/health")"
echo "$health"
jq --exit-status '.status == "ok" and .database == "ok"' <<<"$health" >/dev/null ||
    fail "API health is not ok"
curl --silent --show-error --fail --insecure --dump-header - --output /dev/null "$base/api/health" |
    grep --quiet --ignore-case '^cache-control: no-store' || fail "API responses may be cached"

echo "Web app"
index="$(curl --silent --show-error --fail --insecure "$base/")"
grep --quiet '<div id="app">' <<<"$index" || fail "the web app's index page did not load"
# A page the router handles falls back to the index, so refreshing it works.
curl --silent --show-error --fail --insecure --output /dev/null "$base/integrations" ||
    fail "a page of the web app did not fall back to the index"

echo "The end-to-end test harness is not in this image"
# It can erase the database, so only the e2e image has it (the Dockerfile's e2e target).
code="$(curl --silent --insecure --output /dev/null --write-out '%{http_code}' --request POST \
    "$base/api/__test__/database/clean")"
[[ "$code" = 404 ]] || fail "the test harness answered $code, but only the e2e image has it"

echo "TLS 1.3 only"
curl --silent --show-error --fail --insecure --tlsv1.3 --tls-max 1.3 --output /dev/null "$base/" ||
    fail "TLS 1.3 was refused"
if curl --silent --insecure --tls-max 1.2 --output /dev/null "$base/"; then
    fail "a connection with TLS 1.2 or older was accepted"
fi

echo "HTTP redirects to HTTPS"
location="$(curl --silent --output /dev/null --write-out '%{http_code} %{redirect_url}' \
    "http://localhost:${http_port}/settings" || true)"
[[ "$location" = "301 ${base}/settings" ]] || fail "expected '301 ${base}/settings', got '$location'"

echo "Security headers"
headers="$(curl --silent --show-error --fail --insecure --dump-header - --output /dev/null "$base/")"
for header in strict-transport-security content-security-policy x-content-type-options \
    x-frame-options referrer-policy permissions-policy cross-origin-opener-policy; do
    grep --quiet --ignore-case "^${header}:" <<<"$headers" || fail "missing the $header header"
done
csp="$(grep --ignore-case '^content-security-policy:' <<<"$headers")"
for source in "default-src 'self'" "frame-ancestors 'none'" "object-src 'none'"; do
    grep --quiet --fixed-strings "$source" <<<"$csp" || fail "the CSP is missing \"$source\""
done
if grep --quiet --ignore-case '^server:.*[0-9]' <<<"$headers"; then
    fail "the Server header reveals a version"
fi

echo "Unknown host names are refused during the TLS handshake"
if curl --silent --insecure --output /dev/null --resolve "unknown.example:${https_port}:127.0.0.1" \
    "https://unknown.example:${https_port}/"; then
    fail "a TLS connection for an unknown host name was accepted"
fi

echo "Smoke test passed"
