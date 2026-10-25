# Quick start

AresGate runs as one container. It holds everything: the web app, the API, the database and a
web server with TLS.

## What you need

- A computer that stays on, with [Docker](https://docs.docker.com/get-docker/). The published
  image supports amd64 and arm64.
- Docker Compose and `make` only if you want to build from source or use the helper commands
  below.
- A name for the server on your network, such as `aresgate.example.com`, pointing at its address.
  Use the same name every time you browse to it. Passkeys only work at the name they were
  created for, and not at an IP address, and stop working if you change the name.

## Run a published image without source code

The release image contains the web app, API, database and web server; you do not need to clone
the repository or build anything. This starts the latest release, publishes HTTPS on port 443
and HTTP-to-HTTPS redirection on port 80, and keeps the database and settings in a Docker volume:

```sh
docker run --pull=always --detach \
  --name aresgate \
  --restart unless-stopped \
  --publish 443:8443 \
  --publish 80:8080 \
  --add-host host.docker.internal:host-gateway \
  --env ARESGATE_SERVER_NAME=aresgate.example.com \
  --env ARESGATE_HTTPS_PORT=443 \
  --mount type=volume,source=aresgate-data,target=/data \
  --read-only \
  --tmpfs /run \
  --tmpfs /tmp \
  --tmpfs /var/cache/nginx \
  --tmpfs /etc/nginx/conf.d \
  --tmpfs /etc/nginx/aresgate \
  --cap-drop ALL \
  --cap-add CHOWN \
  --cap-add DAC_OVERRIDE \
  --cap-add FOWNER \
  --cap-add SETGID \
  --cap-add SETUID \
  --cap-add KILL \
  --security-opt no-new-privileges:true \
  ghcr.io/brianbaggs35/aresgate:latest
```

Set `ARESGATE_SERVER_NAME` to the name you will use in your browser. If ports 80 or 443 are
already in use, change the host side of `--publish`; when changing the HTTPS port, also set
`ARESGATE_HTTPS_PORT` to that host port. Docker's `EXPOSE` metadata alone does not publish ports,
so omitting `--publish` makes the container unreachable from the host.

The container creates a self-signed certificate on first start. To use your own certificate,
mount a folder containing `fullchain.pem` and `privkey.pem` at `/certs` with
`--mount type=bind,source=/path/to/certs,target=/certs,readonly`. Follow the setup-code
instructions below with `docker logs aresgate`.

## Install

To build AresGate from source with Compose instead:

```sh
git clone https://github.com/brianbaggs35/AresGate.git
cd AresGate
cp .env.example .env
```

Open `.env` and set at least `ARESGATE_SERVER_NAME` to the name you will browse to. The other
settings have working defaults:

| Setting | Default | What it does |
| --- | --- | --- |
| `ARESGATE_SERVER_NAME` | `localhost` | The name you browse to |
| `ARESGATE_HTTPS_PORT` | `443` | The port on this computer for HTTPS |
| `ARESGATE_HTTP_PORT` | `80` | The port that redirects to HTTPS |
| `TZ` | `UTC` | Time zone, e.g. `America/Halifax` |
| `ARESGATE_API_WORKERS` | `2` | How many API processes to run |
| `ARESGATE_SECRET_KEY` | made for you | The key that encrypts what AresGate stores. Only set it to bring a key from another server ([Operations](operations.md#the-app-secret-key)) |
| `ARESGATE_SESSION_IDLE_MINUTES` | `30` | How long a sign-in can sit unused before it ends |
| `ARESGATE_SESSION_MAX_HOURS` | `12` | The longest a sign-in lasts, however busy |

Then build and start it:

```sh
make up
```

The first build takes a few minutes. When it's done, `make ps` shows the container's health.

## Set up your account

A new install has no account, and anyone who reaches the page first could take it, so AresGate
asks for a setup code that only someone who can read its log has. Run `make logs` and look for
the box near the start:

```
================================================================
 AresGate is ready to be set up.
 Open https://aresgate.example.com and enter this setup code:

     K7QD-3MWX-9HPA
```

Open that address. AresGate asks for the code (step 1), then for a username and a password
(step 2). Use a long password, such as a few words in a sentence: at least 12 characters, and
nothing like your username or the server's name. You are signed in as soon as the account exists.

After that, AresGate asks you to sign in with that username and password. Your sign-in lasts
until it has sat unused for 30 minutes, and ends when you choose **Sign out** from the account
button at the top right. **Status** shows what AresGate and the programs under it are doing,
with a text to copy into a bug report. **Settings** is where the account lives. Its **Activity**
page lists the most recent sign-ins, wrong guesses and sign-outs, so you can see whether anyone
else has tried, and **Sign-ins** lists the browsers that are signed in now, so you can sign out any you don't
recognise. **Account** changes the password and adds an authenticator app, so that signing in asks
for a code from it as well as the password ([Operations](operations.md#signing-in)).

The code changes each time the container starts until the account exists, and stops working
once it has been used, so a later start prints no code. If you lose the code, `make restart`
prints a new one. Five wrong codes in a row make you wait a minute before trying again.

## Certificates

AresGate serves HTTPS with TLS 1.3 only, using the first of these that applies:

- **A Let's Encrypt certificate that AresGate gets for you** (`make cert`, below). Every browser
  trusts it, so there is no warning.
- **Your own certificate.** Put the full chain in `certs/fullchain.pem` and the private key in
  `certs/privkey.pem` (the `certs` folder next to `docker-compose.yml`), then `make restart`.
  After you renew it, `make cert-reload` makes AresGate use the new one without a restart.
- **No certificate.** AresGate makes a self-signed one for your server name when it first
  starts, and keeps it in its data volume. It's fully encrypted, but your browser will warn you
  once. If you change `ARESGATE_SERVER_NAME`, it makes a new one.

The container's health check uses the certificate the way a browser does, so an expired one, or
one for another name, shows as unhealthy in `make ps`.

### Getting a Let's Encrypt certificate (IONOS DNS)

`make cert` gets a free certificate from [Let's Encrypt](https://letsencrypt.org/) with the
*DNS challenge*: it proves you own the domain by adding a short-lived record to its DNS, through
IONOS's API. Nothing from the internet has to reach your server, so AresGate can stay on a
private address, and you can use a name that points at it there. You need:

- A domain whose DNS is hosted at IONOS, and `ARESGATE_SERVER_NAME` in `.env` set to a name in
  it, such as `aresgate.example.com`. A certificate can't be made for `localhost` or an IP
  address.
- An IONOS API key for the DNS API.

**Create the IONOS API key.** IONOS describes this in its
[getting started guide](https://developer.hosting.ionos.com/docs/getstarted). In short: sign in
to the [IONOS developer portal](https://developer.hosting.ionos.com/) with your IONOS account,
open the page for API keys and create one. IONOS shows a *public prefix* and a *secret*, and
shows the secret only once. The key you give AresGate is the two joined with a dot:
`<prefix>.<secret>`. The key can change the DNS of every domain in your IONOS account, so keep it
as private as a password, and delete it in the portal if it leaks or you stop using this.

**Get the certificate.**

```sh
make cert
```

The first time it asks for the IONOS key and keeps it in `acme/ionos-api-key`, which only you
can read. (To skip the question, create that file yourself, holding the key on one line.) Then
it adds the DNS record, waits for it to spread, which can take a few minutes, gets the
certificate, saves it in `certs/` and reloads AresGate with it. Running it accepts Let's
Encrypt's [subscriber agreement](https://letsencrypt.org/repository/). To let Let's Encrypt know
how to reach you, add `ARESGATE_ACME_EMAIL=you@example.com` to `.env` first.

The ACME client (the program that talks to Let's Encrypt) runs from a pinned container image, so
nothing is installed on your computer. The folder `acme/` holds its account key, the
certificate it made and your IONOS key. It is not in the AresGate image or container (only
`certs/` is), and git ignores it.

**Renew it.** A Let's Encrypt certificate lasts 90 days, and is renewed once fewer than 30 are
left. `make cert-renew` does that, and does nothing when the certificate isn't due, so run it
daily from cron:

```cron
17 3 * * * cd /path/to/aresgate && make cert-renew >> /var/log/aresgate-cert.log 2>&1
```

(Cron's `PATH` is short. If it can't find `make` or `docker`, put a `PATH=` line at the top of
the crontab.) Renewal saves the new certificate in `certs/` and reloads nginx with it, so
AresGate doesn't restart and nobody is signed out. Add `FORCE=1` (`make cert-renew FORCE=1`) to
renew before it's due. If a reload is refused, [Operations](operations.md#certificates) says why.

If `make cert` gives up waiting for the DNS record, the DNS server your computer uses probably
can't see your domain's public records (a server that answers for your domain itself does that).
Set `ARESGATE_ACME_RESOLVERS=1.1.1.1:53` in `.env` to have it look there instead.

## Run a published release instead of building it

If you have cloned the repository, releases can also be started with `make pull`. Set these in
`.env`, using the repository's name in lowercase and a version from its releases:

```sh
ARESGATE_IMAGE=ghcr.io/brianbaggs35/aresgate
ARESGATE_VERSION=0.0.3
```

and run `make pull` instead of `make up`. This is the way to run AresGate on a server that
shouldn't have build tools. To run without a checkout at all, use the `docker run` command above.

## Update

- From a release without a checkout: run `docker rm -f aresgate`, then run the command above
  again with the updated image tag. The `aresgate-data` volume is kept. From a release with a
  checkout: set a newer `ARESGATE_VERSION` in `.env` and run `make pull`.
- From the source: `git pull`, then `make up` (or `make rebuild` to rebuild every layer, which
  also fetches the newest security fixes for the operating system's packages).

Your data lives in a Docker volume, so it is kept. Run `make backup` first
([Operations](operations.md#backups)).

## Stop

`make down` stops AresGate and keeps your data. `make logs` follows its logs.
