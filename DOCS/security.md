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
- Certificates: a certificate from `make cert` is obtained by a pinned ACME client image run as
  your user, never inside AresGate's container. The IONOS API key it uses is a file only you can
  read, passed to the client as a file rather than in its command line or environment, and the
  `acme` folder is excluded from the image build. The container only ever sees the certificate
  and its key, mounted read-only. A replacement certificate is checked (key, name, expiry)
  before it is served, so a wrong one can't take AresGate down at renewal time.
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
- The credentials AresGate holds for the things it talks to (a firewall's API key, an AI
  provider's key) are encrypted with AES-256-GCM before they reach the database, using a key
  made from the app secret key with HKDF, one for each purpose (integrations and AI providers).
  Each is also tied to the row it belongs to, so it can't be opened with another key, as
  another kind of value, or copied onto another row. A copy of the database on its own reveals
  none of them, and a test checks that no password, key or recovery code appears anywhere in a
  dump of every table.
- Credentials only go in. The API stores, replaces and deletes them and says which are set, but
  no route returns one, and a request that is refused doesn't quote what it was sent. Only the
  code that talks to the integration opens a credential. Every store and delete is in the
  audit log, with its name and never its value.
- `make rotate-secret-key` changes the app secret key and seals everything again with the new
  one, in a single transaction, so a value that can't be opened changes nothing
  ([Operations](operations.md#changing-the-app-secret-key)).

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
  Its own addresses are the server name (`ARESGATE_SERVER_NAME`) and `localhost`, with the
  HTTPS port (`ARESGATE_HTTPS_PORT`) when it isn't 443, which are the only names the web server
  answers to: it refuses a connection that asks for any other, such as an IP address, before a
  request is read. So `https://localhost` works on the computer that runs AresGate, whatever the
  server name is, and a refused change says which addresses to use.
- Changing the password needs the current one, so a sign-in left open on a borrowed computer
  can't change it. The new one has to pass the same rules as a new account's, and not be the one
  in use. It ends every other sign-in in the same step, so a stolen sign-in doesn't survive it,
  and the audit log records it with how many were ended. A wrong current password counts towards
  the same lockout as at the sign-in page, and says 403 and not 401, so the web app doesn't
  take it for the sign-in having ended.
- Each sign-in keeps the address and browser name it was made from (cut short and stripped of
  control characters, as the audit log's are), and `GET /api/auth/sessions` lists the live ones
  for the account, with the one asking marked. Any other can be ended
  (`POST /api/auth/sessions/{id}/end`), or all of them at once
  (`POST /api/auth/sessions/end-others`); neither can end the sign-in that asks, since signing
  out does that. Only a sign-in's hash is stored, so nothing listed can be used to take it over.
- Five wrong passwords in a row lock the account for a minute, and each wrong one after that
  doubles the wait, up to an hour. The same happens to an address that has made five wrong
  attempts, whatever names it tried, and to the setup code. While locked, even the right
  password is refused. The cost is that anyone who can reach the sign-in page can keep you out
  for a while by guessing wrong on purpose; they still can't get in.
- A wrong username and a wrong password get the same answer in the same time, so the sign-in
  page doesn't tell anyone which names exist.

**The second step**

- An account can add an authenticator app: any app that shows six-digit codes, such as the ones
  built into password managers. AresGate makes a random 160-bit key and shows it as a QR code
  and as text. The step only counts once a code from the app has proved the app has the key, so
  a typing mistake can't lock the account out. Turning it on also makes ten recovery codes, 60
  bits each and shown once.
- With it on, the right password is not enough. It earns a challenge that is good for five
  minutes and can't be forged without the app secret key, and the sign-in finishes with a code
  from the app or a recovery code. A wrong password gets the same answer as ever, so the sign-in
  page doesn't say whether an account has a second step.
- A code from the app works once, so one that was watched being typed is no use to anyone
  else, and a recovery code works once. The codes use HMAC-SHA1 because every authenticator app
  does; what protects the account is that guesses are limited and each code is single-use.
- Wrong codes lock the account and the address exactly like wrong passwords do. A right
  password does not reset that count on an account with a second step, only a right code does,
  so someone who knows the password can't use the sign-in page to wipe their guesses at the
  code.
- The app's key is encrypted with AES-256-GCM, using a key made from the app secret key (HKDF,
  one for each purpose) and tied to the account, so it can't be opened with another key, as
  another kind of value or on another account's row. Recovery codes are kept as HMAC-SHA256
  hashes made with a key of their own, so a copy of the database can't be used to guess either
  offline.
- Making new recovery codes, which ends the old ones, needs a current code, and turning the
  step off needs the password and a current code, so a sign-in left open on a borrowed computer
  can't do either. Wrong answers there count towards the same lockout, and say 403 and not
  401, so the web app doesn't take them for the sign-in having ended. A code isn't used up when
  the password next to it was wrong.
- If the phone and the recovery codes are both lost, whoever runs the server can turn the step
  off with `make two-factor-off` ([Operations](operations.md#signing-in)). It ends the
  account's sign-ins and leaves an event in the audit log.

**Passkeys**

- A passkey signs in with the unlock a device already has, such as a fingerprint, a face or a
  PIN, with nothing typed, not even the username. It takes the place of the password and of the
  second step together, because the device has to unlock it itself (WebAuthn's "user
  verification" is required, and a passkey a device doesn't unlock on its own is refused), so
  an account with an authenticator app signs in with a passkey without a code.
- The private key never leaves the device. AresGate keeps the public key, the passkey's name and
  how often it has been used, so a copy of the database signs in nobody and there is nothing in
  it to seal.
- A passkey belongs to the server name (`ARESGATE_SERVER_NAME`). A browser offers it only on a
  page served from that name, which is why a look-alike site can't ask for it. So an IP address
  can't be used, and if you change the server name the passkeys stop working: remove them and
  add them again. Browsers also want HTTPS, except at `localhost`.
- Each sign-in asks the device to sign a random challenge. A challenge is good for five minutes
  and for one try, right or wrong, so a recorded answer is no use. The answer has to come from
  AresGate's own address, for this server name, with the user present and verified, and sign
  what was asked. Keys of three kinds are taken (ES256, EdDSA and RS256, which covers every
  device) and no attestation is asked for, because AresGate has no reason to care who made the
  device.
- A device's count of sign-ins has to go up, so a copy of a passkey that is used next to the
  original is refused and recorded against the account. Devices that don't count, such as
  synced passkeys that always report zero, are left alone.
- Wrong answers count towards the address's lockout, like wrong passwords, and a locked address
  is refused even a right passkey. They don't count against any account, because nobody has
  said whose account they are after, so guessing at passkeys can't keep the owner out.
- Adding a passkey and removing one need the password, so a sign-in left open on a borrowed
  computer can't put its own passkey on the account or take away the ones the owner would use to
  get back in. Wrong passwords there count towards the same lockout as at the sign-in page, and
  say 403 and not 401, so the web app doesn't take them for the sign-in having ended.
- An account can have 20 passkeys. The password still signs in, so a lost device costs nothing
  but a trip to Settings to remove its passkey.

**The audit log**

- Setting up, signing in (and every wrong guess), signing out and the log's own housekeeping are
  recorded, each with the time, the account, the address the request came from and the browser's
  name. Turning the second step on or off, wrong codes and new recovery codes are recorded too,
  and so is the command that turns the step off. Adding and removing a passkey, and signing in
  with one, are recorded, and so is a passkey whose count went backwards. Storing or deleting a
  credential and changing the app secret key are recorded as well. The features that follow
  (settings and the integrations) add their own events.
- The database refuses to change or delete an event, so a bug in AresGate can't rewrite
  history. The one exception is the clean-up that deletes events older than
  `ARESGATE_AUDIT_RETENTION_DAYS` (a year unless you change it), which records how many it
  deleted. Someone with access to the database can still switch that protection off, as they
  can anything, so it guards against mistakes rather than against them.
- It never holds a password, a setup code or a token. A wrong username that isn't an account is
  recorded without the name, because people sometimes type their password where it goes. Text
  from the browser is stripped of control characters and cut short before it is kept, so it
  can't forge a line.
- The list is for whoever is signed in: `GET /api/audit/events`, newest first, filtered by
  `action` (repeat it), `outcome`, `username`, `since` and `until`, a page at a time with
  `before` and `limit`. The web app's Settings area shows the latest 20 on its Activity page.

**The status page**

- `GET /api/status` is for whoever is signed in. It holds versions, sizes, states and times and
  no secret: what an integration last reported is shown as the integration wrote it, which is
  text from another system, so the web app prints it as plain text and nothing more.
- The text made for bug reports replaces the URLs, IP addresses and host names in what an
  integration reported, so it can be pasted into a public issue without giving away where
  anything is on your network.
- To tell you which certificate browsers are shown, the API opens a TLS connection to nginx on
  the container's own loopback address and reads the certificate without checking it, because
  the question is what it is and not whether to trust it. Nothing is sent over that connection,
  and it never leaves the container.
- The container's figures come from the kernel's files (`/proc` and the cgroup), and nginx's
  version from the package database. AresGate runs no other program to find them out.

**The collector worker**

- It is a separate process in the container, run as the same unprivileged user as the API, that
  makes requests to the integrations and listens on nothing, so it adds no way in.
- It uses the same client as the settings pages, which refuses addresses outside your home
  network (and the cloud metadata address), applies the certificate settings you chose, follows
  no redirects, limits how large an answer can be and how long a request takes, and blanks
  secrets out of every message and log line. Its credentials come from the same encrypted store
  and are opened only for the length of a run.
- Each job has a timeout, only a few run at once, and a failing one backs off, so a broken or
  slow integration can't use up the container's resources. What an integration answered is kept
  to a short description, as in the API log, and shown as plain text.
- `GET /api/collectors` is for whoever is signed in, and says no more than the Status page.

**Logs**

- The API logs one JSON object per line and tags each with the ID of its request, which nginx
  makes and passes on, so a problem can be followed through every layer.
- Anything that looks like a secret is blanked out before it is written, in three ways: by
  name (whatever follows `password`, `token`, `cookie`, `authorization`, `secret`, `api_key`,
  `csrf`, `otp`, a setup or recovery code and the like), by shape (a password hash, a bearer
  token, a private key, a setup code, the password in a database URL), and by value (the app
  secret key, wherever it turns up). It's a last line of defence, such as for the parameters in a
  database error, and the code still doesn't log secrets on purpose.
- A request's line records its path and not its query string. A failure that isn't handled is
  logged with its traceback, but the answer says only that something went wrong, with the
  request's ID in the `X-Request-ID` header so it can be found in the log.

## Planned

These are being built, in this order, and are not in AresGate yet:

- The pages where you enter the credentials for OPNsense, ntopng, Wazuh and AI providers. The
  store they will use is in AresGate already; you can replace a credential but never read it
  back.
- Logging that redacts secrets.
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
