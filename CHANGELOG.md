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
  ([DOCS/security.md](DOCS/security.md)).
- The web app's frame: a menu at the side that shrinks to icons (and remembers it), a bar at the
  bottom on a phone, a skip link for keyboards, and the page's title on top, in the light, dark
  ("mission control") and system themes.
- An audit log of sign-ins (and wrong guesses), sign-outs and setup, kept for a year
  (`ARESGATE_AUDIT_RETENTION_DAYS`), which the database refuses to change or delete, listed by
  `GET /api/audit/events` with filters ([DOCS/security.md](DOCS/security.md)).
- The web app's pages for these: setting up an account in two steps (the setup code, then a
  username and password), signing in and out, and a Security page with the account and its
  recent activity. Pages are closed to anyone who isn't signed in, and a sign-in that ends while
  a page is open sends you back to the sign-in page and on to where you were.
- A second step when signing in, with an authenticator app (RFC 6238 codes): the API makes a
  key to scan or type in, turns the step on once a code from the app proves it works, and gives
  ten single-use recovery codes. The key is encrypted with the app secret key, recovery codes
  are kept as keyed hashes, a code works once, and wrong codes count towards the same lockout
  as wrong passwords ([DOCS/security.md](DOCS/security.md)).
- The web app's pages for it: a Two-step verification card on the Security page to add an
  authenticator app (a QR code, a link for the same device and the key to type in), save the
  recovery codes, make new ones and turn it off, and a second step on the sign-in page that
  takes a code from the app or a recovery code. The activity list names the new events.
- `make two-factor-off ACCOUNT=<username>` turns an account's second step off for someone who
  has lost both the phone and the recovery codes. It ends the account's sign-ins and leaves an
  event in the audit log ([DOCS/operations.md](DOCS/operations.md)).
- An encrypted, write-only store for the credentials of integrations and AI providers: each is
  sealed with AES-256-GCM using a key made from the app secret key for its purpose and tied to
  its row, so a copy of the database reveals none of them. `PUT`, `DELETE` and `GET
  /api/credentials` store, forget and list them, and nothing returns a value. A refused request
  no longer quotes what it was sent. The pages that use it come with the integrations
  ([DOCS/security.md](DOCS/security.md)).
- `make rotate-secret-key` changes the app secret key and seals everything stored again with
  the new one, all or nothing, and leaves an event in the audit log. Recovery codes can't be
  carried over and are made again ([DOCS/operations.md](DOCS/operations.md)).
- Passkeys: sign in with a fingerprint, a face or a device's PIN with nothing typed. A passkey
  takes the place of the password and the authenticator app together (the device has to unlock
  it itself), belongs to the server name, and is checked against a one-time challenge and a
  sign-in count that must go up. The Security page adds and removes them (both ask for the
  password), the sign-in page has a "Sign in with a passkey" button, and the audit log records
  each ([DOCS/security.md](DOCS/security.md)).
- Logs as JSON lines, one per request plus the API's own messages, each tagged with a request ID
  that nginx makes and that comes back in the `X-Request-ID` header, with secrets blanked out
  before anything is written ([DOCS/operations.md](DOCS/operations.md)). `ARESGATE_LOG_FORMAT`
  and `ARESGATE_LOG_LEVEL` change how and how much.
- `/api/system`, for someone signed in: AresGate's version, uptime and the database's version.

### Fixed

- Signing in with a username containing a NUL character no longer ends in a server error.
