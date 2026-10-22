#!/usr/bin/env bash
# Gets a Let's Encrypt certificate for ARESGATE_SERVER_NAME with the DNS-01 challenge, through
# IONOS's DNS API, puts it in certs/ and makes the running container serve it. Run it with
# make, from the folder with docker-compose.yml:
#
#   make cert          the first time (and again after changing ARESGATE_SERVER_NAME)
#   make cert-renew    renews the certificate when it is due, which is every 60 days or so;
#                      run it daily from cron
#   make cert-reload   serves whatever is in certs/ now, without a restart
#
# The ACME client runs from a pinned image, so nothing is installed here. Its account key, the
# certificates it makes and your IONOS API key stay in acme/, which is not part of the image or
# of the container: only certs/ is mounted into it, and only the certificate and its key are
# there. Settings come from the environment, then from .env (plain NAME=value lines):
#
#   ARESGATE_SERVER_NAME     required; the name you browse to, e.g. aresgate.example.com
#   ARESGATE_ACME_EMAIL      optional; where Let's Encrypt can reach you
#   ARESGATE_ACME_RESOLVERS  optional; host:port,host:port of DNS servers that can see the
#                            domain's public records, if yours can't (e.g. 1.1.1.1:53)
#   FORCE=1                  renew now, even if the certificate isn't due
set -euo pipefail

# The ACME client (lego), by version and digest. Dependabot doesn't read scripts, so update the
# two together by hand when there is a newer release.
LEGO_IMAGE=goacme/lego:v5.5.2@sha256:1944e8c36055beec47c7de6f15202b41128be75eea0ffa257f0c14d93c5155fd

cd "$(dirname "${BASH_SOURCE[0]}")/.."

fail() {
    echo "$*" >&2
    exit 1
}

# A setting from the environment, or else from .env.
setting() {
    local name="$1" value="${!1:-}"
    if [[ -z "$value" && -f .env ]]; then
        value="$(sed -n "s/^${name}=//p" .env | tail -n 1)"
        value="${value%[\"\']}"
        value="${value#[\"\']}"
    fi
    printf '%s' "$value"
}

# Moves a file from the ACME client's folder to certs/ in one step, readable by you alone (the
# container's root can read it regardless).
place() {
    local from="$1" to="$2"
    (umask 077 && cp "$from" "$to.new") && mv -f "$to.new" "$to"
}

# Serves what's in certs/ from the running container, or says it will when it starts.
reload() {
    if [[ -n "$(docker compose ps --status running --quiet aresgate)" ]]; then
        docker compose exec -T aresgate /app/docker/reload-certificate.sh
    else
        echo "AresGate isn't running. It serves the certificate in certs/ when it starts."
    fi
}

# The IONOS key is kept in a file only you can read, and handed to the client as a file, so it
# is never in a process list or an environment.
require_api_key() {
    local file=acme/ionos-api-key key
    [[ -s "$file" ]] && return
    [[ -t 0 ]] || fail "There's no IONOS API key in $file. Put it there as <prefix>.<secret> (DOCS/quick-start.md says how to get one)."
    read -rsp "IONOS API key (<prefix>.<secret>): " key
    echo
    [[ "$key" =~ ^[^[:space:]]+\.[^[:space:]]+$ ]] || fail "That doesn't look like an IONOS API key: it is a prefix and a secret with a dot between them."
    (umask 077 && printf '%s\n' "$key" >"$file")
}

obtain() {
    local name email resolvers
    name="$(setting ARESGATE_SERVER_NAME)"
    email="$(setting ARESGATE_ACME_EMAIL)"
    resolvers="$(setting ARESGATE_ACME_RESOLVERS)"

    [[ -n "$name" ]] || fail "Set ARESGATE_SERVER_NAME in .env to the name you browse to, e.g. aresgate.example.com."
    [[ "$name" == localhost || "$name" =~ ^[0-9.]+$ || "$name" == *:* ]] &&
        fail "A certificate is for a domain name you own, not $name. Set ARESGATE_SERVER_NAME in .env."
    [[ "$name" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]] ||
        fail "ARESGATE_SERVER_NAME is $name, which isn't a domain name in lower case."
    if [[ "${1:-}" == renew && ! -s "acme/certificates/$name.crt" ]]; then
        fail "There's no certificate for $name to renew yet. Run make cert first."
    fi

    mkdir -p -m 0700 acme certs
    require_api_key

    local args=(run --path /data --accept-tos --dns ionos --domains "$name" --no-random-sleep)
    [[ -z "$email" ]] || args+=(--email "$email")
    [[ -z "$resolvers" ]] || args+=(--dns.resolvers "$resolvers")
    [[ "${FORCE:-}" != 1 ]] || args+=(--renew-force)

    # Running it as you keeps what it writes in acme/ yours.
    docker run --rm --user "$(id -u):$(id -g)" --volume "$PWD/acme:/data" \
        --env IONOS_API_KEY_FILE=/data/ionos-api-key "$LEGO_IMAGE" "${args[@]}"

    [[ -s "acme/certificates/$name.crt" && -s "acme/certificates/$name.key" ]] ||
        fail "The ACME client didn't leave a certificate for $name in acme/certificates."
    place "acme/certificates/$name.crt" certs/fullchain.pem
    place "acme/certificates/$name.key" certs/privkey.pem
    reload
}

case "${1:-}" in
get) obtain get ;;
renew) obtain renew ;;
reload) reload ;;
*) fail "Usage: scripts/certificate.sh get|renew|reload (run it with make cert, make cert-renew or make cert-reload)." ;;
esac
