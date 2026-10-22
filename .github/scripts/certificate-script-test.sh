#!/usr/bin/env bash
# Tests scripts/certificate.sh (make cert, make cert-renew, make cert-reload) with a stand-in
# for docker, which records what it is asked to do and writes the files the ACME client would.
# That checks what the script reads, refuses, passes on, places and reloads, without Let's
# Encrypt or IONOS. Needs no Docker, so run it from anywhere.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fail() {
    echo "::error::$1" >&2
    exit 1
}

# What a run of the script sees: a copy of it in its own folder, with the stand-in first on PATH.
site="$work/site"
mkdir -p "$work/bin" "$site/scripts"
cp "$repo/scripts/certificate.sh" "$site/scripts/"
log="$work/docker.log"
cat >"$work/bin/docker" <<'SHIM'
#!/usr/bin/env bash
echo "$*" >>"$SHIM_LOG"
if [[ "$1" == compose && "$2" == ps ]]; then
    [[ "${SHIM_RUNNING:-}" != 1 ]] || echo abc123
elif [[ "$1" == run ]]; then
    [[ "${SHIM_LEGO_FAILS:-}" != 1 ]] || exit 1
    # Writes the certificate where the volume maps /data, named after the domain asked for.
    for arg in "$@"; do
        case "$arg" in
        *:/data) data="${arg%:/data}" ;;
        esac
    done
    for ((i = 1; i <= $#; i++)); do
        [[ "${!i}" != --domains ]] || domain="${*:i+1:1}"
    done
    mkdir -p "$data/certificates"
    echo "certificate ${SHIM_ISSUE:-1} for $domain" >"$data/certificates/$domain.crt"
    echo "key ${SHIM_ISSUE:-1} for $domain" >"$data/certificates/$domain.key"
fi
SHIM
chmod +x "$work/bin/docker"

name=aresgate.example.com
server_name_setting="ARESGATE_SERVER_NAME=$name"
chain=certs/fullchain.pem
key=certs/privkey.pem
reload_call="compose exec -T aresgate /app/docker/reload-certificate.sh"

# Runs the script in the site with the given settings, from a stdin that is not a terminal.
# Sets output to what it printed, and status to its exit code. docker's calls are in $log.
certificate() {
    : >"$log"
    status=0
    output="$(cd "$site" && env -i PATH="$work/bin:$PATH" HOME="$work" SHIM_LOG="$log" "$@" \
        bash scripts/certificate.sh "$subcommand" </dev/null 2>&1)" || status=$?
}

expect_success() {
    local what="$1"
    [[ "$status" == 0 ]] || fail "$what failed: $output"
}

expect_failure() {
    local why="$1" message="$2"
    [[ "$status" != 0 ]] || fail "$why: it should have failed"
    grep --quiet --fixed-strings -- "$message" <<<"$output" || fail "$why: it should say '$message', but said '$output'"
    ! grep --quiet '^run ' "$log" || fail "$why: it ran the ACME client anyway"
}

# Docker was asked (or, for expect_no_calls, not asked) for each of the arguments given.
expect_calls() {
    local what="$1" wanted
    shift
    for wanted in "$@"; do
        grep --quiet --fixed-strings -- "$wanted" "$log" || fail "$what: docker should have been asked for '$wanted', but was asked: $(cat "$log")"
    done
}

expect_no_calls() {
    local what="$1" unwanted
    shift
    for unwanted in "$@"; do
        ! grep --quiet --fixed-strings -- "$unwanted" "$log" || fail "$what: docker should not have been asked for '$unwanted'"
    done
}

# A file in the site says what it should, and only its owner can read it.
expect_file() {
    local file="$1" content="$2" mode="$3"
    [[ "$(cat "$site/$file")" == "$content" ]] || fail "$file should say '$content', but says '$(cat "$site/$file")'"
    [[ "$(stat -c %a "$site/$file")" == "$mode" ]] || fail "$file should be mode $mode, but is $(stat -c %a "$site/$file")"
}

echo "It needs a server name that a certificate can be for"
subcommand="get"
certificate
expect_failure "no server name" "Set ARESGATE_SERVER_NAME"
for refused in localhost 192.168.1.5 "::1" Aresgate.Example.com nodots -aresgate.example.com "aresgate..example.com"; do
    certificate "ARESGATE_SERVER_NAME=$refused"
    expect_failure "the name $refused" "ARESGATE_SERVER_NAME"
done

echo "It asks for the IONOS API key when it can't prompt"
certificate "$server_name_setting"
expect_failure "no API key" "no IONOS API key in acme/ionos-api-key"

echo "It won't renew a certificate that was never made"
mkdir -p "$site/acme"
echo "prefix.secret" >"$site/acme/ionos-api-key"
subcommand="renew"
certificate "$server_name_setting"
expect_failure "renewing before getting" "Run make cert first"

echo "It gets a certificate, saves it for the container, and tells a stopped one nothing to reload"
subcommand="get"
certificate "$server_name_setting"
expect_success "getting a certificate"
expect_calls "the ACME client" "--domains $name" --accept-tos "--dns ionos" "--user $(id -u):$(id -g)" \
    "--env IONOS_API_KEY_FILE=/data/ionos-api-key" "goacme/lego:v5." "@sha256:"
expect_no_calls "the ACME client" --email --renew-force prefix.secret
expect_file "$chain" "certificate 1 for $name" 600
expect_file "$key" "key 1 for $name" 600
expect_no_calls "a stopped container" " exec "
grep --quiet "isn't running" <<<"$output" || fail "it should say AresGate isn't running, but said '$output'"

echo "It makes a running container serve the new certificate"
certificate "$server_name_setting" SHIM_RUNNING=1 SHIM_ISSUE=2 FORCE=1
expect_success "getting a certificate again"
expect_calls "forcing" --renew-force "$reload_call"
expect_file "$chain" "certificate 2 for $name" 600

echo "It takes its settings from .env, and the environment wins"
cat >"$site/.env" <<ENV
ARESGATE_SERVER_NAME=ignored.example.com
ARESGATE_ACME_EMAIL="me@example.com"
ARESGATE_ACME_RESOLVERS=1.1.1.1:53,9.9.9.9:53
ENV
subcommand="renew"
certificate "$server_name_setting" SHIM_ISSUE=3
expect_success "renewing"
expect_calls ".env" "--email me@example.com" "--dns.resolvers 1.1.1.1:53,9.9.9.9:53"
expect_calls "the environment" "--domains $name"
expect_no_calls "the environment" ignored.example.com
expect_file "$chain" "certificate 3 for $name" 600
printf 'ARESGATE_SERVER_NAME=%s\n' "from-env-file.example.com" >"$site/.env"
subcommand="get"
certificate
expect_success "using the name in .env"
expect_calls ".env" "--domains from-env-file.example.com"
rm "$site/.env"

echo "A failed run leaves the certificate being used alone"
certificate "$server_name_setting" SHIM_LEGO_FAILS=1 SHIM_RUNNING=1 SHIM_ISSUE=4
[[ "$status" != 0 ]] || fail "it should fail when the ACME client does"
expect_file "$chain" "certificate 1 for from-env-file.example.com" 600
expect_no_calls "a failed run" " exec "

echo "It reloads on its own too"
subcommand="reload"
certificate SHIM_RUNNING=1
expect_success "reloading"
expect_calls "reloading" "$reload_call"
expect_no_calls "reloading" "run "

echo "It says how to use it"
subcommand="nonsense"
certificate
expect_failure "an unknown command" "Usage: scripts/certificate.sh"
echo "The certificate script does what it should"
