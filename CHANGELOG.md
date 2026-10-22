# Changelog

Every release's notes are here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- The single container: nginx with TLS 1.3, the API, PostgreSQL 18 and the web app, built on
  Chainguard's Wolfi and hardened as described in [DOCS/security.md](DOCS/security.md).
- A status page showing whether the API and the database are up, with light and dark themes.
- `make` commands to run, update, back up, develop, test and check AresGate.
- Continuous integration: pytest, Vitest and Playwright (desktop and phone) with coverage,
  pyright, ESLint, SonarQube Cloud, CodeQL, Trivy, pip-audit, npm audit, zizmor and Dependabot.
- A workflow that publishes the image for amd64 and arm64 with signed provenance and an SBOM
  when a release is made ([DOCS/releasing.md](DOCS/releasing.md)).
- The README, these docs, and the security policy.
- The app secret key that will encrypt stored credentials and authenticator-app keys: the API
  won't start without one of at least 32 characters. The container makes it, or you supply it
  in `.env` or as a Docker secret ([DOCS/operations.md](DOCS/operations.md)).
- Setting up and signing in to the API: a one-time setup code in the container's log creates the
  one account, passwords are hashed with Argon2id and checked against a password policy,
  sign-ins are kept in `HttpOnly` `__Host-` cookies with a security token for every change, and
  wrong guesses lock the account, the address and the setup code for a growing wait
  ([DOCS/security.md](DOCS/security.md)). The web app's pages for these arrive next.
- The web app's frame: a menu at the side that shrinks to icons (and remembers it), a bar at the
  bottom on a phone, a skip link for keyboards, and the page's title on top, in the light, dark
  ("mission control") and system themes.
- An audit log of sign-ins (and wrong guesses), sign-outs and setup, kept for a year
  (`ARESGATE_AUDIT_RETENTION_DAYS`), which the database refuses to change or delete, listed by
  `GET /api/audit/events` with filters ([DOCS/security.md](DOCS/security.md)).
- Logs as JSON lines, one per request plus the API's own messages, each tagged with a request ID
  that nginx makes and that comes back in the `X-Request-ID` header, with secrets blanked out
  before anything is written ([DOCS/operations.md](DOCS/operations.md)). `ARESGATE_LOG_FORMAT`
  and `ARESGATE_LOG_LEVEL` change how and how much.
- `/api/system`, for someone signed in: AresGate's version, uptime and the database's version.

### Fixed

- Signing in with a username containing a NUL character no longer ends in a server error.
