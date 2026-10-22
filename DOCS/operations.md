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

### Restoring

Restore into a freshly started AresGate that nobody has used yet, running the same release as
the backup or a newer one:

1. Start AresGate (`make up` or `make pull`) on the new server and wait for `make ps` to say
   it's healthy.
2. Restore the key. Put the text from `make secret-key` into `/data/secrets/secret.key` in the
   volume (for example with `make shell`), keeping the file readable only by the `aresgate`
   user, then `make restart`.
3. Restore the database:

   ```sh
   docker compose exec -T -u aresgate aresgate \
     pg_restore -h /run/postgresql -d aresgate --clean --if-exists --no-owner \
     < backups/aresgate-<date>-<time>.dump
   ```

4. `make restart`, so the API starts from the restored data.

## Logs and health

- `make logs` follows the logs of everything in the container: nginx, the API and PostgreSQL.
- `make ps` shows whether the container is healthy. The health check goes through the whole path
  (nginx, TLS, the API and the database), so it also fails when the certificate has expired or
  is for the wrong name.
- `make shell` opens a shell in the container, and `make psql` a database shell.

The status page (the first page you see) shows whether the API and the database are up.

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
