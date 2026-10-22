#!/usr/bin/env bash
# Tests TLS certificates in the AresGate container: the one in certs/ is served and passes the
# health check, a renewed one is served after `make cert-reload` with no restart, one that is for
# another name, doesn't match its key or has expired is refused and the old one keeps being
# served, and a container that starts with an expired one reports itself unhealthy. Uses (and
# removes) the files in certs/, so run it from the repository root with the image already built,
# e.g. in CI after the build.
set -euo pipefail

compose=(docker compose)
https_port="${ARESGATE_HTTPS_PORT:-443}"
chain=certs/fullchain.pem
key=certs/privkey.pem
work="$(mktemp -d)"
trap 'docker compose down --volumes >/dev/null 2>&1 || true; rm -rf "$chain" "$key" "$work"' EXIT

fail() {
    echo "::error::$1" >&2
    exit 1
}

# A certificate for a name, good for a month, in certs/ or at the given paths.
make_certificate() {
    local name="$1" chain_path="${2:-$chain}" key_path="${3:-$key}"
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -noenc -days 30 \
        -subj "/CN=$name" -addext "subjectAltName=DNS:$name" -keyout "$key_path" -out "$chain_path" 2>/dev/null
}

# Like make_certificate, but it ran out in 2020. openssl req can't back-date one until OpenSSL 3.4,
# so this signs it with openssl ca.
make_expired_certificate() {
    local name="$1"
    openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -noenc -subj "/CN=$name" \
        -addext "subjectAltName=DNS:$name" -keyout "$key" -out "$work/expired.csr" 2>/dev/null
    printf '[ca]\ndefault_ca=c\n[c]\ndatabase=%s/index\nnew_certs_dir=%s\nserial=%s/serial\ndefault_md=sha256\npolicy=p\ncopy_extensions=copy\n[p]\ncommonName=supplied\n' \
        "$work" "$work" "$work" >"$work/ca.cnf"
    : >"$work/index"
    echo 01 >"$work/serial"
    openssl ca -selfsign -batch -config "$work/ca.cnf" -keyfile "$key" -in "$work/expired.csr" \
        -out "$chain" -startdate 20200101000000Z -enddate 20200102000000Z >/dev/null 2>&1
}

# The fingerprint of the certificate the container is serving, for localhost.
served() {
    openssl s_client -connect "localhost:$https_port" -servername localhost -tls1_3 </dev/null 2>/dev/null |
        openssl x509 -noout -fingerprint -sha256
}

in_certs() {
    openssl x509 -in "$chain" -noout -fingerprint -sha256
}

reload() {
    "${compose[@]}" exec -T aresgate /app/docker/reload-certificate.sh
}

health_check() {
    "${compose[@]}" exec -T aresgate python /app/docker/healthcheck.py
}

expect_served() {
    local when="$1"
    [[ "$(served)" == "$(in_certs)" ]] || fail "$when: the container isn't serving the certificate in certs/"
}

expect_reload_refused() {
    local why="$1" message="$2" before output
    before="$(served)"
    if output="$(reload 2>&1)"; then
        fail "$why: the certificate was loaded"
    fi
    grep --quiet --fixed-strings -- "$message" <<<"$output" || fail "$why: it should say '$message', but said '$output'"
    [[ "$(served)" == "$before" ]] || fail "$why: the container stopped serving the certificate it had"
}

mkdir -p certs

echo "A certificate in certs/ is served, and passes the health check"
make_certificate localhost
"${compose[@]}" down --volumes >/dev/null 2>&1
"${compose[@]}" up --detach --no-build --wait --wait-timeout 180
expect_served "starting with a certificate"
health_check || fail "the health check failed with a good certificate"
started="$(docker inspect --format '{{.State.StartedAt}}' aresgate)"

echo "A renewed certificate is served after a reload, with no restart"
make_certificate localhost
[[ "$(served)" != "$(in_certs)" ]] || fail "the test needs a different certificate"
reload
expect_served "reloading"
[[ "$(docker inspect --format '{{.State.StartedAt}}' aresgate)" == "$started" ]] || fail "the container restarted"
health_check || fail "the health check failed after the certificate was renewed"
./.github/scripts/smoke-test.sh >/dev/null || fail "the API didn't answer after the reload"

echo "A certificate that isn't fit to serve is refused, and the one being served stays"
make_certificate localhost
cp "$chain" "$work/good.pem"
reload
make_certificate other.example.com
expect_reload_refused "a certificate for another name" "isn't for localhost"
make_certificate localhost "$work/other-chain.pem" "$work/other-key.pem"
cp "$work/good.pem" "$chain"
cp "$work/other-key.pem" "$key"
expect_reload_refused "a key that doesn't match" "isn't the one for the certificate"
make_expired_certificate localhost
expect_reload_refused "an expired certificate" "has expired"
rm "$chain" "$key"
expect_reload_refused "no certificate" "There is no certificate to load"

echo "A container that starts with an expired certificate reports itself unhealthy"
make_expired_certificate localhost
"${compose[@]}" down --volumes >/dev/null 2>&1
"${compose[@]}" up --detach --no-build
for _ in $(seq 60); do
    [[ -z "$(served)" ]] || break
    sleep 2
done
expect_served "starting with an expired certificate"
if output="$(health_check 2>&1)"; then
    fail "the health check passed with an expired certificate"
fi
grep --quiet --ignore-case 'expired' <<<"$output" || fail "the health check should say the certificate expired, but said '$output'"
echo "Certificates are served, renewed without a restart, and checked"
