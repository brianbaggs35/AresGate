#!/usr/bin/env bash
# Checks a container whose server name isn't localhost, the way someone who sets
# ARESGATE_SERVER_NAME to a domain of their own uses it: at that name, and at https://localhost on
# the computer that runs it, where the name may not point. Both addresses must take a change (a
# wrong setup code, which the API only answers once it has accepted where the request came from),
# a change from another website must be refused, the log must name both addresses, and plain HTTP
# must send each visitor on to the address they used. Run it from the repository root against a
# container that has just started on empty data, with ARESGATE_SERVER_NAME set to a name other
# than localhost and the ports in the environment, as the smoke test is.
set -euo pipefail

name="${ARESGATE_SERVER_NAME:?Set ARESGATE_SERVER_NAME to the name the container was started with}"
https_port="${ARESGATE_HTTPS_PORT:-443}"
http_port="${ARESGATE_HTTP_PORT:-80}"
# What a browser adds to an address when the port isn't the default one.
suffix=""
[[ "$https_port" = 443 ]] || suffix=":$https_port"

fail() {
    echo "::error::$1" >&2
    exit 1
}

[[ "$name" != localhost ]] || fail "the server name has to be one other than localhost"

# The name points at this computer for curl, as it would in DNS or a hosts file.
resolve=(--resolve "$name:$https_port:127.0.0.1" --resolve "$name:$http_port:127.0.0.1")

status=""
body=""

# change ORIGIN HOST: sends a wrong setup code to HOST over HTTPS, as a browser on a page at ORIGIN
# would. The status code and body are left in $status and $body.
change() {
    local origin="$1" host="$2" answer
    answer="$(curl --silent --show-error --insecure "${resolve[@]}" --request POST \
        --header "Origin: $origin" --header 'Content-Type: application/json' \
        --data '{"code":"AAAA-AAAA-AAAA","username":"probe","password":"not-used-1234"}' \
        --write-out $'\n%{http_code}' "https://$host$suffix/api/setup")"
    status="${answer##*$'\n'}"
    body="${answer%$'\n'*}"
}

echo "Setting up is let through at the server name and at localhost"
for host in "$name" localhost; do
    change "https://$host$suffix" "$host"
    [[ "$status" = 403 ]] || fail "$host: expected 403 for a wrong setup code, got $status ($body)"
    grep --quiet --fixed-strings "That setup code isn't right." <<<"$body" ||
        fail "$host: the change was refused before the setup code was checked ($body)"
done

echo "A change from another website is refused"
for host in "$name" localhost; do
    change "https://evil.example" "$host"
    [[ "$status" = 403 ]] || fail "$host: expected 403 for another website, got $status ($body)"
    grep --quiet --fixed-strings "The request didn't come from AresGate." <<<"$body" ||
        fail "$host: a change from another website was not refused for where it came from ($body)"
done

echo "The log names both addresses"
docker compose logs --no-color aresgate |
    grep --quiet --fixed-strings "Open https://$name$suffix or https://localhost$suffix and enter this setup code" ||
    fail "the log doesn't say to open https://$name$suffix or https://localhost$suffix"

echo "HTTP goes on to the address that was used"
for host in "$name" localhost; do
    redirect="$(curl --silent --output /dev/null --write-out '%{http_code} %{redirect_url}' \
        "${resolve[@]}" "http://$host:$http_port/settings" || true)"
    [[ "$redirect" = "301 https://$host$suffix/settings" ]] ||
        fail "$host: expected '301 https://$host$suffix/settings', got '$redirect'"
done
