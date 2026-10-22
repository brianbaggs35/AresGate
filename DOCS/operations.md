# Operations

## Where the data is

Everything AresGate keeps is in one Docker volume, `aresgate-data`, mounted at `/data` in the
container (Docker names it `aresgate_aresgate-data`):

| Path in the volume | What it is |
| --- | --- |
| `postgres/` | The database |
| `secrets/secret.key` | The app secret key, made on first start. Only the API can read it |
| `certs/` | The self-signed certificate, when you haven't provided your own |

`make down` stops AresGate and keeps the volume. Deleting the volume (`docker volume rm`, or
`docker compose down --volumes`) deletes all of it, so back it up first.

## Backups

```sh
make backup
```

writes a dump of the database to `backups/aresgate-<date>-<time>.dump` on this computer. Do it
before every update, and on a schedule (for example from cron).

AresGate encrypts the credentials it stores, and the authenticator-app keys, with the app secret
key. A database backup on its own can't be read without it, so keep a copy of the key somewhere
safe and **apart from the backups**:

```sh
make secret-key
```

### The app secret key

The container makes the key the first time it starts, and keeps it in the data volume. To use a
key from somewhere else, such as one you restored from a backup, give it to the container before
it starts. It must be at least 32 characters, and AresGate refuses to start with a shorter one,
saying so in `make logs`. Either:

- put it in `.env` as `ARESGATE_SECRET_KEY=<the key>`, or
- keep it in a file and put the file's path in `.env` as `ARESGATE_SECRET_KEY_FILE=<path in the
  container>`. This is how a Docker secret is used: save the key in a file next to
  `docker-compose.yml`, add a `docker-compose.override.yml` that mounts it, and point
  `ARESGATE_SECRET_KEY_FILE` at the mount.

  ```yaml
  services:
    aresgate:
      secrets:
        - aresgate_secret_key
  secrets:
    aresgate_secret_key:
      file: ./secret-key.txt
  ```

  with `ARESGATE_SECRET_KEY_FILE=/run/secrets/aresgate_secret_key` in `.env`. The file can be
  readable by you alone.

A key you supply is used instead of any the container made earlier, and the container makes none
of its own. `make secret-key` only shows a key the container made, so keep a copy of the one you
supplied. Either way the container hands the key only to the API, and takes `ARESGATE_SECRET_KEY`
out of the environment of everything else it runs. After changing `.env`, run `make up` (or `make pull`) again so the
container is created with the new setting: `make restart` keeps the old one.

Changing the key after AresGate has stored credentials makes those credentials unreadable, so
only do it to bring back the key that encrypted them.

### Restoring

Restore into a freshly started AresGate that nobody has used yet, running the same release as
the backup or a newer one:

1. Set the old server's key as `ARESGATE_SECRET_KEY` in `.env` (see
   [The app secret key](#the-app-secret-key)), then start AresGate (`make up` or `make pull`) on
   the new server and wait for `make ps` to say it's healthy.
2. Restore the database:

   ```sh
   docker compose exec -T -u aresgate aresgate \
     pg_restore -h /run/postgresql -d aresgate --clean --if-exists --no-owner \
     < backups/aresgate-<date>-<time>.dump
   ```

3. `make restart`, so the API starts from the restored data.

## Logs and health

- `make logs` follows the logs of everything in the container: nginx, the API and PostgreSQL.
- `make ps` shows whether the container is healthy. The health check goes through the whole path
  (nginx, TLS, the API and the database), so it also fails when the certificate has expired or
  is for the wrong name.
- `make shell` opens a shell in the container, and `make psql` a database shell.

The status page (the first page you see) shows whether the API and the database are up.

## Signing in

AresGate has one account. [Quick start](quick-start.md#set-up-your-account) shows how to create
it with the setup code from the log.

- **Locked out.** Five wrong passwords lock the account for a minute, then two, four and so on up
  to an hour; the page says how long. Behind Docker Desktop, or any setup that hides who is
  connecting, every browser can look like the same address, so one person's wrong guesses can
  make others wait too. The wait ends by itself.
- **A sign-in ended.** It ends after 30 minutes idle or 12 hours in all. Change that with
  `ARESGATE_SESSION_IDLE_MINUTES` and `ARESGATE_SESSION_MAX_HOURS` in `.env`, then `make up` or
  `make restart`.
- **Forgot the password.** There is no way to change or reset it from the web app yet. To start
  over without losing anything else, delete the account and set up again:

  ```sh
  make psql
  DELETE FROM users;
  \q
  make restart
  ```

  Then follow the setup steps with the code in `make logs`. Anyone who can run these commands
  can already read everything on the server, so this opens nothing new.

## Certificates

See [Quick start](quick-start.md#certificates). After you renew a certificate, `make restart`
makes AresGate use the new one.

## Changing the server name or the ports

Edit `.env` and run `make up` again (or `make pull` if you run a release). A new server name
means a new self-signed certificate, unless you provide your own.

## Updating

See [Quick start](quick-start.md#update). Updates apply any database changes themselves when the
API starts.

## The container's limits

The container's filesystem is read-only apart from the data volume and a few temporary folders,
and it has only the few Linux capabilities it needs to switch each program to its own
unprivileged user. If you run it some other way than `docker-compose.yml`, keep those settings
([Security](security.md)).
