# Releasing AresGate

A release is published by creating a GitHub release, and that is the only thing that runs the
Release workflow (`.github/workflows/release.yml`): no pull request, push or manual run does, and
saving a draft doesn't. It builds the container image, checks it and publishes it to the GitHub
Container Registry at `ghcr.io/<owner>/<repo>`, in lowercase (for this repository,
`ghcr.io/brianbaggs35/aresgate`).

## Creating a release

1. Make sure CI is green on `master` and the commit you want to release is on it.
2. On GitHub, go to **Releases > Draft a new release**, create a tag from `master` named like
   `v1.4.0` (or `1.4.0`), and publish the release. Mark it **pre-release** for a release
   candidate such as `v1.4.0-rc.1`.
3. Watch **Actions > Release**. It takes about ten minutes.

The workflow refuses a tag that isn't a version, or that isn't on `master`.

## What the workflow does

For each CPU (amd64 and arm64, each on a runner of its own) it:

1. Builds the production image, upgrading every package in it to the newest fix, and stamps in
   the release's version (Settings > System shows it).
2. Scans it with Trivy. A high or critical vulnerability that has a fix stops the release.
3. Starts it as `docker compose` does, runs the smoke test, then restarts it on the same data
   and tests it again.
4. Pushes the image, but only from the layers that were just tested.

When both pass, it joins the two images into one multi-platform image and tags it:

| Release | Tags |
| --- | --- |
| `v1.4.0` | `1.4.0`, `1.4`, `1` and `latest` |
| `v1.4.0-rc.1` (pre-release) | `1.4.0-rc.1` only, so `latest` stays on the newest stable release |

It then signs the image's **build provenance** and an **SBOM** for each CPU. These attestations
are stored in the repository's attestations, not as registry tags: registry-attached attestation
artifacts can appear in the package UI as `sha256-...` pull commands even though they aren't
container images. The SBOMs are also attached to the release as
`aresgate-<version>-linux-<arch>.spdx.json`.

## Checking an image

Anyone can check that an image was built by this repository's workflow:

```sh
gh attestation verify oci://ghcr.io/<owner>/<repo>:1.4.0 --repo <owner>/<repo>
```

## Changing the workflow

Because only a published release runs it, a change to the workflow or its script isn't tried in a
pull request: CI lints it (actionlint and zizmor), and ShellCheck checks the script, but the first
real run is a release. After changing it, publish a pre-release such as `v0.0.2-rc.1` to try it,
and delete that release and its tag afterwards if you like.

## Making the image public

GitHub creates a package for the image the first time it's published, and a new package is private.
Once, after the first release, open the package (the repository's **Packages** sidebar, then
**Package settings**) and change its visibility to **Public** so anyone can pull it without
logging in.

## Secrets

`CHAINGUARD_PULL_USERNAME` and `CHAINGUARD_PULL_PASSWORD` are optional: the base image is public,
and a pull token only raises Chainguard's pull limits. Publishing uses the workflow's own token, so
nothing else is needed.
