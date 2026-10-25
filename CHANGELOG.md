# Changelog

Every release's notes are here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- OPNsense's health, traffic and gateways, read every minute and kept as metrics: the load,
  uptime, memory and disk space, the processors' use, the bytes, packets and errors of each
  interface, and whether each gateway is up and how its link is doing. They are four jobs on the
  Collection card, each needing its own privilege in OPNsense
  ([DOCS/integrations.md](DOCS/integrations.md#health-traffic-and-gateways)).

## 0.0.3

### Added

- Storage for the numbers the integrations measure over time, such as a firewall's load or an
  interface's traffic, for the collectors that read them to save and the charts to draw. Each is
  kept for 30 days unless `ARESGATE_METRIC_RETENTION_DAYS` says otherwise, or an integration is
  given a period of its own, as for events ([DOCS/operations.md](DOCS/operations.md)).

### Fixed

- Every build of the image now gets the newest fix of every package, as
  [DOCS/security.md](DOCS/security.md) says. The Wolfi base image holds its packages at the
  versions it shipped with, which kept `apk upgrade` from moving them, so a vulnerability fixed
  in one of them (CVE-2026-111497 in brotli) failed the image scan until the base was replaced.

## 0.0.2

### Added

- Instructions for running a published image directly with Docker, without cloning the source
  repository or building the image ([DOCS/quick-start.md](DOCS/quick-start.md)).

### Fixed

- Keep build provenance and SBOM attestations in GitHub's attestation store instead of publishing
  them as `sha256-...` registry tags that appear to be pullable images
  ([DOCS/releasing.md](DOCS/releasing.md)).

## 0.0.1

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
- TLS certificates: `make cert` gets a Let's Encrypt certificate for the server name through the
  DNS challenge with an IONOS API key (using a pinned ACME client image, so nothing is installed),
  `make cert-renew` renews it when due and is meant for cron, and `make cert-reload` has nginx
  serve a changed certificate with no restart. A replacement is checked (key, name, expiry)
  before it is served. The container's health check already verifies the certificate as a
  browser would ([DOCS/quick-start.md](DOCS/quick-start.md#certificates)).
- Logs as JSON lines, one per request plus the API's own messages, each tagged with a request ID
  that nginx makes and that comes back in the `X-Request-ID` header, with secrets blanked out
  before anything is written ([DOCS/operations.md](DOCS/operations.md)). `ARESGATE_LOG_FORMAT`
  and `ARESGATE_LOG_LEVEL` change how and how much.
- `/api/system`, for someone signed in: AresGate's version, uptime and the database's version.
- Integration pages: one card for each of OPNsense, ntopng, Wazuh and CrowdSec showing what it
  provides, whether it is connected and when AresGate last reached it, and a page for each to
  connect, test and disconnect it. OPNsense's page finds the services that run on it (Suricata,
  CrowdSec, OpenVPN, WireGuard, IPsec, Unbound, Dnsmasq, Kea and more) and has an optional
  Zenarmor connection. Addresses must be on a private network and are never redirected, the
  certificate is checked (or trusted by a pasted authority or a pinned fingerprint), secrets are
  write-only, and every request is kept in an API log without secrets or query strings for
  `ARESGATE_API_LOG_RETENTION_DAYS` days ([DOCS/integrations.md](DOCS/integrations.md)).

- A Settings area in the web app, which replaces the Security page: **Account** (who is signed
  in, changing the password, passkeys and two-step verification), **Sign-ins** (the browsers that
  are signed in, with a button to sign out one or all the others) and **Activity**. Changing the
  password ends every other sign-in. The pages are tabs on a phone and a list at the side
  elsewhere ([DOCS/security.md](DOCS/security.md)).
- A **Status** page in the web app, and `GET /api/status` behind it, for when something seems
  wrong: AresGate's version, commit, build time and uptime, the versions of Python, nginx and
  PostgreSQL, the database's size, connections and migration, the TLS certificate browsers are
  shown and how long it has left, the container's CPUs, load, memory and disk, and the clock
  compared with the browser's. Each integration is listed as a part that works, has a problem or
  is off, with a link to its page, and anything that needs a look is said first. A card holds
  the same facts as text for a bug report, with addresses left out, and a button to copy it
  ([DOCS/operations.md](DOCS/operations.md#logs-and-health)).
- The image now records which commit it was built from and when (`make up` and the release
  workflow pass them in), so the Status page can say which build is running.
- The collector worker: a program of its own in the container, next to the API, that reads from
  the integrations on a schedule. Each job runs on its own timer for each connection, waits
  longer after every failure (30 seconds, then 1 minute, doubling up to its normal interval),
  stops after its timeout, and goes through the same client as the settings pages, so the
  address checks, certificate checks and API log are the same. The first job is a connection
  check every five minutes, which keeps an integration's status and the services found on it
  current without anyone pressing Test. Each job's last run, next run and last error are shown
  on the integration's page (a **Collection** card) and on the Status page, which also says
  whether the worker itself is running. `GET /api/collectors` has the same. Setting
  `ARESGATE_COLLECTORS_ENABLED=false` keeps the worker running but idle
  ([DOCS/operations.md](DOCS/operations.md#the-collector-worker)).
- Normalized event storage: what the collectors read is kept as events in one shape (time,
  integration, kind, severity, addresses and ports, the rule that fired, a summary, a hash that
  stops the same event being stored twice, and the program's own record), in a table for each
  week so old events leave by dropping a table. They are kept for 30 days
  (`ARESGATE_EVENT_RETENTION_DAYS`), or for as long as is set for an integration with
  `PUT /api/events/storage/<integration>`, and `GET /api/events/storage` says how many each has
  and how old the oldest is. The API removes the old ones when it starts and every six hours
  ([DOCS/operations.md](DOCS/operations.md#stored-events)).
- The first collector that stores events: OPNsense's firewall log, read every 30 seconds. Each
  line becomes an event with its time, the interface, what the firewall did (a block is low
  severity, anything else info), the direction, protocol, addresses and ports and the rule's
  description, and the line itself is kept beside it. The firewall's log has no time zone, so
  AresGate works the zone out from the firewall's clock and says so on the Collection card if the
  two clocks are more than five minutes apart instead of storing times it can't trust
  ([DOCS/integrations.md](DOCS/integrations.md#the-firewall-log)).
- OPNsense's Suricata alerts, read every minute when Suricata is installed: each alert becomes an
  event with its signature, interface, protocol, addresses and ports and whether Suricata
  blocked it (medium severity, or low if it did), and the record is kept beside it without the
  packet that set it off. Collectors now skip a service that testing the connection found isn't
  installed, so a firewall without Suricata has no such job
  ([DOCS/integrations.md](DOCS/integrations.md#suricata-alerts)).

### Fixed

- Signing in with a username containing a NUL character no longer ends in a server error.
