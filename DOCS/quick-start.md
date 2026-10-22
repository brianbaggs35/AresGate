# Quick start

AresGate runs as one container. It holds everything: the web app, the API, the database and a
web server with TLS.

## What you need

- A computer that stays on, with [Docker](https://docs.docker.com/get-docker/) and Docker
  Compose. Anything that runs Docker will do; the image is published for amd64 and arm64.
- `make`, which runs the short commands below. (Without it, every target in the `Makefile` is a
  `docker compose` command you can run yourself.)
- A name for the server on your network, such as `aresgate.example.com`, pointing at its address.
  Use the same name every time you browse to it. Passkeys, when they arrive, only work at the
  name they were created for, and not at an IP address.

## Install

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

Open that address, enter the code and choose a username and a password. Use a long password,
such as a few words in a sentence: at least 12 characters, and nothing like your username or the
server's name. You are signed in as soon as the account exists.

The code changes each time the container starts until the account exists, and stops working
once it has been used, so a later start prints no code. If you lose the code, `make restart`
prints a new one. Five wrong codes in a row make you wait a minute before trying again.

## Certificates

- **Your own certificate.** Put the full chain in `certs/fullchain.pem` and the private key in
  `certs/privkey.pem` (the `certs` folder next to `docker-compose.yml`), then `make restart`.
  A certificate from a public authority such as Let's Encrypt is the best choice, because every
  browser trusts it. After you renew it, run `make restart` again.
- **No certificate.** AresGate makes a self-signed one for your server name when it first
  starts, and keeps it in its data volume. It's fully encrypted, but your browser will warn you
  once. If you change `ARESGATE_SERVER_NAME`, it makes a new one.

The container's health check uses the certificate the way a browser does, so an expired one, or
one for another name, shows as unhealthy in `make ps`.

## Run a published release instead of building it

Releases are published as images (see [Releasing](releasing.md)). To run one, add these to
`.env`, using the repository's name in lowercase and a version from its releases:

```sh
ARESGATE_IMAGE=ghcr.io/brianbaggs35/aresgate
ARESGATE_VERSION=0.0.1
```

and run `make pull` instead of `make up`. This is the way to run AresGate on a server that
shouldn't have build tools.

## Update

- From a release: set a newer `ARESGATE_VERSION` in `.env` and run `make pull`.
- From the source: `git pull`, then `make up` (or `make rebuild` to rebuild every layer, which
  also fetches the newest security fixes for the operating system's packages).

Your data lives in a Docker volume, so it is kept. Run `make backup` first
([Operations](operations.md#backups)).

## Stop

`make down` stops AresGate and keeps your data. `make logs` follows its logs.
