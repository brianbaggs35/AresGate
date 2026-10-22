#!/bin/sh
# Puts a certificate and its private key where nginx reads them, in place of any that are there.
# nginx's master process (root) and nothing else reads the key; the group is the same as for
# the certificate so a reload by a worker's user would work too. Each file is written under a
# temporary name and renamed, so nginx never finds half of one.
#
# Usage: install-certificate.sh FULLCHAIN PRIVATE_KEY
set -eu
# The key is never readable by anyone else, not even before the chmod below.
umask 077

chain="$1"
key="$2"
tls_dir=/run/aresgate/tls

install_file() {
    source_file="$1"
    name="$2"
    cp "$source_file" "$tls_dir/.$name.new"
    chown root:nginx "$tls_dir/.$name.new"
    chmod 0640 "$tls_dir/.$name.new"
    mv -f "$tls_dir/.$name.new" "$tls_dir/$name"
}

install_file "$chain" cert.pem
install_file "$key" key.pem
