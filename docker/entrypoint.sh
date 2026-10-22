#!/bin/sh
# Prepares the data volume, database, app secret, TLS certificate and nginx config, then
# hands the container to supervisord. Runs as root; every long-running process drops
# privileges.
set -eu

DATA_DIR=/data
PGDATA="$DATA_DIR/postgres"
SECRETS_DIR="$DATA_DIR/secrets"
TLS_DIR=/run/aresgate/tls
: "${ARESGATE_MODE:=production}"
: "${ARESGATE_SERVER_NAME:=localhost}"
: "${ARESGATE_HTTPS_PORT:=443}"
export ARESGATE_MODE ARESGATE_SERVER_NAME ARESGATE_HTTPS_PORT

log() { echo "aresgate: $*"; }

# Runs a command as a service account, without a login shell or PAM.
as_user() {
    user="$1"
    shift
    setpriv --reuid="$user" --regid="$user" --init-groups "$@"
}

umask 022
mkdir -p "$PGDATA" "$SECRETS_DIR" "$DATA_DIR/certs" /run/postgresql /run/nginx /run/aresgate \
    "$TLS_DIR" /var/cache/nginx /etc/nginx/aresgate /etc/nginx/conf.d

# ---- Postgres ----------------------------------------------------------------------
# A volume created by an older image can hold the database under a different user ID.
pg_owner="$(stat -c %u "$PGDATA")"
[ -e "$PGDATA/PG_VERSION" ] && pg_owner="$(stat -c %u "$PGDATA/PG_VERSION")"
if [ "$pg_owner" != "$(id -u postgres)" ]; then
    log "handing the database files to the postgres user"
    chown -R postgres:postgres "$PGDATA"
fi
chown postgres:postgres "$PGDATA" /run/postgresql
chmod 0700 "$PGDATA"
# Only postgres writes its socket here; everyone else just needs to reach it.
chmod 0755 /run/postgresql
chown nginx:nginx /run/nginx /var/cache/nginx

# The database listens only on a unix socket and trusts the OS user via peer auth, so no
# password exists to leak and nothing outside the container can connect. The builtin
# C.UTF-8 collation doesn't depend on the operating system's locale data.
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    log "initialising database"
    as_user postgres initdb -D "$PGDATA" --encoding=UTF8 --locale=C \
        --locale-provider=builtin --builtin-locale=C.UTF-8 \
        --auth-local=peer --auth-host=reject >/dev/null
    cat >>"$PGDATA/postgresql.conf" <<CONF

# AresGate
listen_addresses = ''
unix_socket_directories = '/run/postgresql'
password_encryption = 'scram-sha-256'
log_destination = 'stderr'
log_min_messages = warning
CONF
    as_user postgres pg_ctl -D "$PGDATA" -w -o "-c listen_addresses=''" start >/dev/null
    as_user postgres psql -X -v ON_ERROR_STOP=1 -q -h /run/postgresql -d postgres <<SQL
CREATE ROLE aresgate LOGIN;
CREATE DATABASE aresgate OWNER aresgate;
REVOKE ALL ON DATABASE aresgate FROM PUBLIC;
SQL
    as_user postgres pg_ctl -D "$PGDATA" -w -m fast stop >/dev/null
fi

# ---- App secret --------------------------------------------------------------------
# Encrypts sensitive values, such as integration credentials and authenticator-app keys,
# before they reach the database, so a database dump on its own doesn't reveal them. Only the
# API can read it. The first start makes one in the data volume. A key you supply, in
# ARESGATE_SECRET_KEY or in the file ARESGATE_SECRET_KEY_FILE names (a Docker secret), is used
# instead: it's copied to memory-backed storage that only the API can read, which also works
# for a secret file that only root can read, and is dropped from the environment so no other
# process inherits it. The API checks the key's length when it starts.
if [ -n "${ARESGATE_SECRET_KEY:-}" ]; then
    log "using the app secret key from ARESGATE_SECRET_KEY"
    (umask 077 && printf '%s\n' "$ARESGATE_SECRET_KEY" >/run/aresgate/secret.key)
    unset ARESGATE_SECRET_KEY
    export ARESGATE_SECRET_KEY_FILE=/run/aresgate/secret.key
    chown aresgate:aresgate "$ARESGATE_SECRET_KEY_FILE"
elif [ -n "${ARESGATE_SECRET_KEY_FILE:-}" ]; then
    log "using the app secret key in $ARESGATE_SECRET_KEY_FILE"
    (umask 077 && cat "$ARESGATE_SECRET_KEY_FILE" >/run/aresgate/secret.key)
    export ARESGATE_SECRET_KEY_FILE=/run/aresgate/secret.key
    chown aresgate:aresgate "$ARESGATE_SECRET_KEY_FILE"
elif [ ! -s "$SECRETS_DIR/secret.key" ]; then
    log "generating the app secret key"
    (umask 077 && openssl rand -base64 32 >"$SECRETS_DIR/secret.key")
fi
chown -R aresgate:aresgate "$SECRETS_DIR"
chmod 0700 "$SECRETS_DIR"
[ ! -e "$SECRETS_DIR/secret.key" ] || chmod 0400 "$SECRETS_DIR/secret.key"

# ---- TLS -----------------------------------------------------------------------------
# Use the certificate in /certs (from `make cert`, which gets one from Let's Encrypt through a
# DNS challenge, or one you bring) when present; otherwise generate a self-signed one for
# ARESGATE_SERVER_NAME. `make cert-reload` swaps in a renewed one without a restart.
chown root:nginx "$TLS_DIR"
chmod 0750 "$TLS_DIR"
if [ -s /certs/fullchain.pem ] && [ -s /certs/privkey.pem ]; then
    log "using certificate from /certs"
    /app/docker/install-certificate.sh /certs/fullchain.pem /certs/privkey.pem
else
    SELF_SIGNED="$DATA_DIR/certs/selfsigned"
    if [ ! -s "$SELF_SIGNED.crt" ] || [ "$(cat "$SELF_SIGNED.name" 2>/dev/null)" != "$ARESGATE_SERVER_NAME" ]; then
        log "generating a self-signed certificate for $ARESGATE_SERVER_NAME"
        (umask 077 && openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -noenc -days 825 \
            -subj "/CN=$ARESGATE_SERVER_NAME" \
            -addext "subjectAltName=DNS:$ARESGATE_SERVER_NAME,DNS:localhost,IP:127.0.0.1" \
            -keyout "$SELF_SIGNED.key" -out "$SELF_SIGNED.crt" 2>/dev/null)
        echo "$ARESGATE_SERVER_NAME" >"$SELF_SIGNED.name"
    fi
    /app/docker/install-certificate.sh "$SELF_SIGNED.crt" "$SELF_SIGNED.key"
fi
export ARESGATE_TLS_CERT="$TLS_DIR/cert.pem" ARESGATE_TLS_KEY="$TLS_DIR/key.pem"

# ---- nginx -----------------------------------------------------------------------------
CONNECT_EXTRA=""
[ "$ARESGATE_MODE" = development ] && CONNECT_EXTRA=" wss:"

# Everything is same-origin: the integrations and threat feeds are fetched by the API, never by
# the browser. Vuetify injects styles at runtime. The single quotes are part of the CSP syntax,
# not shell quoting.
# shellcheck disable=SC2089,SC2090
export ARESGATE_CSP="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'$CONNECT_EXTRA; frame-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'; upgrade-insecure-requests"
if [ "$ARESGATE_HTTPS_PORT" = 443 ]; then ARESGATE_HTTPS_PORT_SUFFIX=""; else ARESGATE_HTTPS_PORT_SUFFIX=":$ARESGATE_HTTPS_PORT"; fi
# nginx also answers to localhost, which the container's own healthcheck connects to.
ARESGATE_SERVER_NAMES="$ARESGATE_SERVER_NAME"
[ "$ARESGATE_SERVER_NAME" = localhost ] || ARESGATE_SERVER_NAMES="$ARESGATE_SERVER_NAME localhost"
export ARESGATE_HTTPS_PORT_SUFFIX ARESGATE_SERVER_NAMES

TEMPLATES=/etc/nginx/aresgate-templates
# Fills in aresgate.conf and security-headers.conf from the variables above.
python3 /app/docker/render-nginx-config.py
cp "$TEMPLATES/api-proxy.conf" /etc/nginx/aresgate/api-proxy.conf
cp "$TEMPLATES/app-$ARESGATE_MODE.conf" /etc/nginx/aresgate/app.conf
nginx -e stderr -t -q

log "starting ($ARESGATE_MODE mode, https://$ARESGATE_SERVER_NAME$ARESGATE_HTTPS_PORT_SUFFIX)"
exec supervisord -c /etc/supervisor/supervisord.conf
