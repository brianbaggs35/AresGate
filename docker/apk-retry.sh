#!/bin/sh
# Runs the command it's given (an apk call) again after a pause when it fails. Packages come
# over the network, and when a download stalls apk installs everything else and exits non-zero;
# running the same command again installs what's missing. Only used while building the image.
set -eu

attempts=8
attempt=1
until "$@"; do
    if [ "$attempt" -ge "$attempts" ]; then
        echo "apk-retry: still failing after $attempts attempts: $*" >&2
        exit 1
    fi
    echo "apk-retry: attempt $attempt of $attempts failed, trying again in $((attempt * 5))s" >&2
    sleep $((attempt * 5))
    attempt=$((attempt + 1))
done
