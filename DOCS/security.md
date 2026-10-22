# Security

AresGate will hold the credentials for your firewall and monitoring tools and read your
network's logs, so it is built to be hard to attack and to leave little to steal. This page says
what protects it today, what is planned, and how every change is checked. To report a problem,
see [SECURITY.md](../SECURITY.md).

## How it is hardened today

**The container**

- Built on Chainguard's Wolfi, which is rebuilt as soon as fixes for vulnerabilities are
  published. Every build upgrades all packages to their newest fixes.
- Nothing runs as one all-powerful user. The container starts as root only so it can start each
  program as its own unprivileged user: PostgreSQL, the API and nginx each have their own.
- `docker-compose.yml` makes the filesystem read-only, drops every Linux capability except the
  few needed to switch users, and forbids gaining new privileges.
- The images are built from packages that are already built (Python wheels, and npm packages
  installed without running their scripts), so installing a dependency never runs its code.

**The network**

- Only HTTPS is served, with TLS 1.3 and nothing older. HTTP only redirects to HTTPS.
- A request for a host name that isn't AresGate's is refused during the TLS handshake.
- Responses carry strict security headers: HSTS, a content security policy that allows only the
  app's own scripts and connections, no framing, no content sniffing, and a strict referrer and
  permissions policy. The server doesn't reveal its version.
- nginx rate-limits the API.
- The API's interactive documentation is off unless it is turned on for development, and the
  health endpoint reveals nothing but whether things work.

**The data**

- PostgreSQL listens only on a unix socket inside the container, and the API connects as the
  operating system user it runs as (peer authentication). There is no database password to leak
  and nothing outside the container can connect.
- The app secret key is made on first start, or supplied by you in `.env` or a Docker secret, and
  can be read only by the API. It must be at least 32 characters, and the API won't start
  without one.

## Planned

These are being built, in this order, and are not in AresGate yet:

- A one-time setup code for the first run, so nobody who reaches the page first can take over.
- A single account that must use an authenticator app or a passkey, with recovery codes.
- Credentials for OPNsense, ntopng, Wazuh and AI providers stored encrypted and write-only: you
  can replace them but never read them back.
- An audit log of sign-ins and changes, and logging that redacts secrets.
- An AI analyst that only reads at first. Hosted AI providers will get addresses and host names
  replaced with stand-ins.

## How every change is checked

Every pull request must pass:

- **CodeQL** (security and quality queries) on the Python, TypeScript and workflow code.
- **SonarQube Cloud**, with zero open issues: a pull request with an open issue fails CI.
- **Trivy** on the source (dependencies, leaked secrets, Dockerfile mistakes) and on the built
  image, failing on any high or critical finding that has a fix.
- **pip-audit** and **npm audit** on the dependencies, and **bandit** on the Python code.
- **zizmor** on the workflow files, which are also pinned: every action is referenced by its
  full commit, never by a tag that could move.
- The tests (pytest, Vitest and Playwright, including accessibility checks), pyright in strict
  mode, ESLint and the container's smoke test, which checks the settings above.

**Dependabot** opens pull requests for new versions and security fixes of the Python and npm
dependencies, the Docker base image and the workflow actions.

Published images are scanned again before they are pushed and come with a signed build
provenance and an SBOM ([Releasing](releasing.md)).
