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

**The account and signing in**

- A fresh install has no account. The container prints a one-time setup code in its log when it
  starts, and creating the account needs it, so nobody who reaches the page first can take
  over. The code is 60 bits of randomness, only its hash is kept, it changes every time the
  container starts until the account exists, and it stops working once it has been used.
- Passwords are hashed with Argon2id (the RFC 9106 low-memory settings), and hashed again with
  stronger settings the next time you sign in if they ever change. A password must have 12 to 128
  characters, must not be one of the most common passwords, a run such as `abcdefghijkl` or
  `qwertyuiopas`, or something made of your username, the server's name or "AresGate". There are
  no demands for capitals or symbols, as [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html)
  advises. Passwords are never checked against a breach list on the internet, because this
  server may not be online and shouldn't tell anyone what you chose.
- Signing in sets a cookie that is `HttpOnly` (scripts can't read it), `Secure`, `SameSite=Strict`
  and named `__Host-aresgate_session`, which makes browsers send it only to this exact host over
  HTTPS. It holds a random token, and only the token's hash is stored, so a copy of the
  database can't be used to sign in. A sign-in ends after 30 minutes idle or 12 hours in all
  (`ARESGATE_SESSION_IDLE_MINUTES`, `ARESGATE_SESSION_MAX_HOURS`), and when you sign out.
- Every change the web app asks for must say it came from AresGate's own address (the `Origin`
  header, which browsers always send and a page on another website can't change), and carry a
  security token that is different for each sign-in and that only AresGate's pages are given.
- Five wrong passwords in a row lock the account for a minute, and each wrong one after that
  doubles the wait, up to an hour. The same happens to an address that has made five wrong
  attempts, whatever names it tried, and to the setup code. While locked, even the right
  password is refused. The cost is that anyone who can reach the sign-in page can keep you out
  for a while by guessing wrong on purpose; they still can't get in.
- A wrong username and a wrong password get the same answer in the same time, so the sign-in
  page doesn't tell anyone which names exist.

## Planned

These are being built, in this order, and are not in AresGate yet:

- A second step when you sign in, with an authenticator app or a passkey, and recovery codes.
  Until then the account is protected by its password alone, so use a long one.
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
