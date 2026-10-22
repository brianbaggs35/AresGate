#!/bin/sh
# Makes the running container serve the certificate now in /certs (the certs folder next to
# docker-compose.yml), without restarting it: nginx reloads, and keeps answering the requests
# it is in the middle of. `make cert-reload` runs this, and so do `make cert` and
# `make cert-renew` after they save a new certificate.
#
# The certificate is checked first. One that has expired, that is for another name or that
# doesn't match its key is refused, and the certificate being served stays.
set -eu

chain=/certs/fullchain.pem
key=/certs/privkey.pem
server_name="${ARESGATE_SERVER_NAME:-localhost}"
served=/run/aresgate/tls/cert.pem

fingerprint() { openssl x509 -noout -fingerprint -sha256; }

if [ ! -s "$chain" ] || [ ! -s "$key" ]; then
    echo "There is no certificate to load: put fullchain.pem and privkey.pem in the certs folder," >&2
    echo "or run make cert to get one from Let's Encrypt." >&2
    exit 1
fi

/app/docker/check-certificate.sh "$chain" "$key" "$server_name"
/app/docker/install-certificate.sh "$chain" "$key"
nginx -e stderr -s reload

# The signal returns at once, and nginx loads the certificate a moment later. Wait until it is
# the one being served, so a failure to load it (which nginx only logs) shows here.
wanted="$(fingerprint <"$chain")"
for _ in 1 2 3 4 5 6 7 8 9 10; do
    now="$(openssl s_client -connect 127.0.0.1:8443 -servername "$server_name" </dev/null 2>/dev/null | fingerprint 2>/dev/null || true)"
    if [ "$now" = "$wanted" ]; then
        echo "AresGate is serving the certificate for $server_name, which expires on $(openssl x509 -in "$served" -noout -enddate | cut -d= -f2)."
        exit 0
    fi
    sleep 1
done
echo "nginx didn't start serving the new certificate. Its log (make logs) says why." >&2
exit 1
