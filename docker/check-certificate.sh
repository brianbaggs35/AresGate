#!/bin/sh
# Checks that a certificate is fit to serve before it replaces the one nginx is using: that it
# can be read, that the private key belongs to it, that it hasn't expired and that it is for the
# server name. Says what is wrong on stderr and exits with 1.
#
# Usage: check-certificate.sh FULLCHAIN PRIVATE_KEY SERVER_NAME
set -eu

chain="$1"
key="$2"
server_name="$3"

fail() {
    echo "$*" >&2
    exit 1
}

openssl x509 -in "$chain" -noout 2>/dev/null || fail "$chain isn't a certificate in PEM form."
# An empty password makes a key that needs one fail here, rather than wait for someone to type.
key_public="$(openssl pkey -in "$key" -passin pass: -pubout 2>/dev/null)" ||
    fail "$key isn't a private key in PEM form, or it is protected by a password."
[ "$(openssl x509 -in "$chain" -noout -pubkey)" = "$key_public" ] ||
    fail "The private key in $key isn't the one for the certificate in $chain."
openssl x509 -in "$chain" -noout -checkend 0 >/dev/null || fail "The certificate in $chain has expired."
openssl x509 -in "$chain" -noout -checkhost "$server_name" | grep -q 'does match' ||
    fail "The certificate in $chain isn't for $server_name."
