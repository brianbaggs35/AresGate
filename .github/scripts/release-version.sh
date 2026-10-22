#!/usr/bin/env bash
# Checks a release's tag and works out what to publish, for the Release workflow: the version
# the image is stamped with, the image's name and the tags it gets. A release's tag has to be a
# semantic version (1.4.0 or v1.4.0, with an optional pre-release suffix such as -rc.1).
# Pre-releases get their exact version as the only tag, so `latest`, `1.4` and `1` stay on the
# newest stable release.
#
# Reads TAG (the release's tag), PRERELEASE (true or false) and GITHUB_REPOSITORY, and writes
# version, image and tags (one per line) to GITHUB_OUTPUT.
set -euo pipefail

fail() {
    echo "::error::$1" >&2
    exit 1
}

semver='^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$'

given="${TAG:?}"

[[ "$given" =~ $semver ]] ||
    fail "'$given' isn't a version. Name the release's tag like v1.4.0 or 1.4.0 (or v1.4.0-rc.1 for a pre-release)."
major="${BASH_REMATCH[1]}"
minor="${BASH_REMATCH[2]}"
suffix="${BASH_REMATCH[4]}"
version="${given#v}"

tags="$version"
if [[ -z "$suffix" && "${PRERELEASE:-false}" != "true" ]]; then
    tags+=$'\n'"$major.$minor"$'\n'"$major"$'\n'"latest"
fi

# Registry names have to be lowercase, but a repository's name can have capitals.
repository="${GITHUB_REPOSITORY:?}"
image="ghcr.io/${repository,,}"

echo "Version $version, published as $image with the tags: ${tags//$'\n'/, }"
{
    echo "version=$version"
    echo "image=$image"
    echo "tags<<EOF"
    echo "$tags"
    echo "EOF"
} >>"${GITHUB_OUTPUT:-/dev/stdout}"
