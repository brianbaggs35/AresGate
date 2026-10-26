# Operations

## Where the data is

Everything AresGate keeps is in one Docker volume, `aresgate-data`, mounted at `/data` in the
container (Docker names it `aresgate_aresgate-data`):

| Path in the volume | What it is |
| --- | --- |
| `postgres/` | The database |
| `secrets/secret.key` | The app secret key, made on first start. Only the API can read it |
| `certs/` | The self-signed certificate, when you haven't provided your own |

The `certs` and `acme` folders next to `docker-compose.yml` are on the computer, not in the
volume: `certs/` holds the certificate and key you use, and `acme/` what `make cert` needs to
renew them ([Certificates](#certificates)). `make backup` doesn't include either. A certificate from
`make cert` is made again by running it; keep a copy of one you brought yourself.

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

Changing `.env` to a different key makes the credentials AresGate has stored, and the keys of
authenticator apps, unreadable, so only do it to bring back the key that encrypted them. To
change the key on purpose, use `make rotate-secret-key` instead, below. (If the key is lost for
good, [turn the second step off](#signing-in) and set it up again.)

### Changing the app secret key

Change the key now and then, and at once if you think someone has seen it:

```sh
make rotate-secret-key
```

This works when the container made the key. It makes a new one, seals everything AresGate
stores again with it (the credentials for your integrations and AI providers, and the keys of
authenticator apps), and replaces the key in the data volume, which AresGate starts using at
once. It is all one transaction, so if anything can't be opened with the current key the command
says which and changes nothing. Then run `make restart`, so that the logs blank out the new key
too, keep a copy of the new key apart from the backups (`make secret-key`), and take a new
backup, because **older backups need the older key**.

Two things to know:

- **Recovery codes end.** They are kept as hashes made with the key and can't be made again
  under a new one, so each account has to make new codes in Settings, on the Account page. Its
  authenticator app keeps working.
- **Do it when nobody is signing in.** For the moment between the data changing and the key file
  being replaced, a request that needs a sealed value can fail. Trying again works.

If you supplied the key in `.env` or as a Docker secret, the container can't change it for you,
so give the command the new key (at least 32 characters) on its standard input, then put the
same key in `.env` or the secret and run `make up` so that AresGate restarts with it. Until it
does, AresGate can't open what it stores.

```sh
docker compose exec -T -u aresgate -w /app/backend aresgate \
    python -m app.cli rotate-secret-key --new-key-file - < new-secret-key.txt
```

If a rotation is cut short, `secret.key.new` can be left beside the key in `secrets/`. If the
stored credentials still open with `secret.key`, the change never happened: delete the new file.
If they don't, move `secret.key.new` over `secret.key`. Either way the next rotation refuses to
run until the leftover file is gone.

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

The **Dashboard** (the first page you see) says what the network has been doing and whether any
of it needs you, as described [below](#the-dashboard). Once you're signed in, the **Status** page
in the menu says more about AresGate itself, and is the place to look first when something
seems wrong. It shows:

- **AresGate**: the version, the commit and time it was built from (set by `make up` and by the
  release workflow, and "Not recorded" where AresGate runs from source), and how long it has
  been running.
- **Software**: Python, nginx and PostgreSQL's versions, the database's size and connections,
  and the migration it is at next to the one this version expects. They differ while an update
  is half done, or when an older image is started on newer data, and the page says so.
- **Certificate**: the one nginx shows browsers for your server name, who issued it and how many
  days it has left. It warns from 14 days before the end.
- **Container**: the CPUs it may use, the load, how much of its memory limit (or the computer's
  memory, where there is no limit) and of the data disk is in use, and whether its clock agrees
  with the computer you are browsing from. A clock that is a minute or more off is flagged,
  since sign-ins and certificates depend on time.
- **Integrations**: each one as working, having a problem (with the last error), not yet
  tested or off, and when it last worked.
- **Collectors**: the worker and each job it runs ([below](#the-collector-worker)), with the same
  states, and the reason when one fails. A job whose integration is already listed with a
  problem isn't listed again at the top of the page.

The **For a bug report** card has the same facts as plain text and a **Copy** button. It has
versions, sizes, states and times, and never an address, a name or a secret: URLs, IP addresses
and host names in what an integration reported are replaced. Paste it into an issue when you
[report a problem](../CONTRIBUTING.md), after a look to be sure it holds nothing you'd rather
keep private.

The same facts are available to a signed-in client as `GET /api/status`, and `/api/system` has
the version, how long AresGate has been running and PostgreSQL's version.

### The collector worker

Reading from the integrations on a schedule is done by the worker, a program of its own in the
container (`docker/start-worker.sh`, started by supervisord next to the API). Keeping it apart
means a slow or unreachable integration, or a bug in one collector, can't slow down or take down
the web app. They share the database and nothing else.

- **What it does.** For each connected integration it runs the jobs that apply to it. Today
  those are a connection check every five minutes, which does what **Test connection** does and
  keeps the integration's status and the services found on it up to date, and, on OPNsense,
  the firewall log every 30 seconds and, if Suricata is installed, its alerts every minute
  ([below](#stored-events)). A service that testing the connection found isn't installed has no
  jobs. The worker also files what the collectors stored into [incidents](#incidents) every 30
  seconds. A job that fails is
  tried again after 30 seconds, then 1 minute, then 2, and so on, but never later than its normal
  interval, and it's stopped if it takes too long. Connecting an integration starts its jobs
  within seconds, saving its settings again runs them straight away, and disconnecting it stops
  them. At most four jobs run at the same time.
- **What it asks.** Every request goes through the same client as the settings pages, so the
  same rules apply (only addresses on your home network, the certificate settings you chose,
  no redirects followed) and each request is in the integration's API log. It opens nothing for
  the network to connect to: it only makes requests.
- **Where to look.** An integration's page has a **Collection** card with each job's state,
  when it last ran and how long it took, when it runs next and why it failed. The Status page
  lists the worker and the jobs. A worker that hasn't reported in for a minute is shown as a
  problem; it reports every 15 seconds. `make logs` shows what it logs, as the API does.
- **Pausing it.** Set `ARESGATE_COLLECTORS_ENABLED=false` in `.env`, then `make up` or
  `make restart`. The worker keeps running and reporting in, and does nothing else, and the
  Status page says collecting is off. The jobs' history is kept, and shown again when it's
  turned back on.
- **Restarting.** The worker starts after the migrations are done, and supervisord restarts it
  if it stops. If it keeps failing, the container stops, as it does for the API.

### Stored events

What the collectors read from the integrations (a firewall block, an alert, a failed login) is
kept as events, in one shape whatever program reported them: when it happened, which integration
and connection, what kind it is, how serious, the addresses and ports, the rule that fired, a
one-line summary and the program's own record of it. Reading the same thing twice, which
overlapping requests do, stores it once. So far the collectors that store events are
OPNsense's [firewall log](integrations.md#the-firewall-log) and
[Suricata alerts](integrations.md#suricata-alerts), CrowdSec's [bans](integrations.md#bans),
Wazuh's [alerts](integrations.md#alerts) and [silent agents](integrations.md#agents), and
ntopng's [flow and host alerts](integrations.md#flow-alerts-and-host-alerts); the others come
with the integrations.

- **How long they're kept.** 30 days. Change that for everything with
  `ARESGATE_EVENT_RETENTION_DAYS` (1 to 3650) in `.env`, then `make up` or `make restart`. An
  integration can keep them for longer or shorter than that, which suits a busy firewall log and
  a quiet alert log. **Settings**, then **Data**, shows each integration's setting, how many
  events it has and when the oldest happened, and **Change** sets it, asking first if that
  removes events already stored. The same is `PUT /api/events/storage/opnsense` with
  `{"days": 7}` (or `{"days": null}` to go back to the default) and `GET /api/events/storage`
  when signed in. Each change is in the audit log.
- **How they go.** Events are stored in a table for each week, so the oldest leave by dropping a
  table, which is instant and gives the disk back. The API removes what's past its retention
  period when it starts and every six hours after that, as it does for the audit log: a week
  that ended before even the longest period began is dropped whole, and what's left is deleted
  by integration and time. Shortening a period takes effect at the next clean-up, and an event
  that is already older than its integration keeps events isn't stored in the first place.
- **What's in them.** An event keeps the program's own record, up to 64 KiB (a larger one is
  replaced by its size), so it may hold addresses, host names and user names from your network.
  It stays in the database and in its backups ([Backups](#backups)), and goes with the
  integration's retention period.
- **If the clock is wrong.** An event dated more than five minutes ahead of AresGate's clock is
  stored as of now, so a wrong clock on another machine can't make a table for next year.

### Stored metrics

The numbers the collectors measure (a firewall's load, the traffic through an interface) are kept
as samples: one number, read from one connection at one moment, under the name of what it
measures (`system.load_1m`) and the labels that tell it apart from the same thing measured
elsewhere (`interface: igc0`). Reading the same moment twice stores it once, and a reading that
isn't a number is left out. So far the collectors that store metrics are OPNsense's
[health, traffic and gateways](integrations.md#health-traffic-and-gateways), how many bans
[CrowdSec](integrations.md#bans) has in force, how many of Wazuh's
[agents](integrations.md#agents) are in each state, and ntopng's
[hosts](integrations.md#hosts-and-the-devices-among-them) and
[interface](integrations.md#the-interfaces-traffic); the others come with the integrations.

- **How long they're kept.** 30 days. Change that for everything with
  `ARESGATE_METRIC_RETENTION_DAYS` (1 to 3650) in `.env`, then `make up` or `make restart`. An
  integration can keep them for longer or shorter, apart from how long it keeps its events:
  the **Measurements** card on the **Data** page in Settings shows and sets it, or, signed in,
  `PUT /api/metrics/storage/opnsense` with `{"days": 90}` (or `{"days": null}` to go back to the
  default) sets it, and `GET /api/metrics/storage` shows each integration's setting, how many
  samples it has and when the oldest was read. Each change is in the audit log.
- **How much room they take.** About 100 bytes a reading, with its indexes. A firewall with two
  interfaces and one gateway gives about 28 readings a minute, which is about 130 MB over the
  default 30 days. Each interface adds seven readings a minute and each gateway four.
- **How they go.** Samples are stored in a table for each week, and leave the way events do: the
  API removes what's past its retention period when it starts and every six hours after that,
  dropping a week that ended before even the longest period began and deleting the rest by
  integration and time. A measured thing that has no samples left is forgotten with them.
  Shortening a period takes effect at the next clean-up.
- **If the clock is wrong.** A sample dated more than five minutes ahead of AresGate's clock is
  stored as of now.

### Stored devices

The devices the collectors see on the network are kept in two tables: `devices`, with one row
for each hardware (MAC) address, and `device_addresses`, with a row for each IP address a device
has had. A device has the host name and the maker of its network card that were last told, and
when it was first and last seen; an address has the same two times. A device that was seen again
is updated, not added, and an address that changed hands is in the rows of both devices, the
one seen with it last having it now. The collectors that fill them are OPNsense's
[ARP table and DHCP leases](integrations.md#devices).

- **How long they're kept.** Until you remove them: there is no retention period for devices yet,
  and nothing reads them yet either.
- **How much room they take.** A few hundred bytes for each device and address, so a home network
  of a hundred devices is a few tens of kilobytes. A device that changes its hardware address
  often is a new device each time, which adds up very slowly.
- **How they're written.** Every run updates the devices it lists, once a minute for the ARP
  table, so the tables are small but see a steady trickle of updates.

### Incidents

An incident is the alerts and bans that belong together, whichever integration reported them:
Suricata's alert, Wazuh's log line and CrowdSec's ban of one address are one incident, not three
rows in three places. It says how serious that is, how sure AresGate is that it is a real attack
and why, and lists the signals in the order they happened. The worker files them (see
[the collector worker](#the-collector-worker)); nothing here needs an AI provider.

- **What counts as a signal.** An alert, or a ban, of low severity or more. The firewall's blocks
  don't: the internet knocks all day and a block says the firewall worked. Instead an incident
  says how many times the firewall turned its address away around then. Alerts of no importance
  (info) and agents going offline aren't signals either.
- **Which incident a signal joins.** The one about the same *subject* that is still going. The
  subject is the address the signal is about: where one end is outside your network and the
  other isn't, the outside one, whichever way the traffic went, so an attack coming in and a
  device calling out to the same address are one incident. Where both are inside, or both
  outside, it is the source. A signal that names no address (such as a log line from a
  host) is about the rule that raised it. Addresses that say nothing, such as `0.0.0.0`,
  loopback, multicast and broadcast, are ignored. An incident has been going until it has been
  quiet for 6 hours; after that, the next signal about the subject starts another, so a scan on
  Monday and another on Friday are two.
- **How serious.** As serious as its most serious signal.
- **How sure.** Confidence is 0 to 100 and is a sum of reasons, each with its points and a
  sentence, which the incident keeps so that you can see why and disagree:

  | Reason | Points |
  | --- | --- |
  | The most serious signal's severity: info 0, low 10, medium 25, high 40, critical 55 | 0 to 55 |
  | Each other program that saw it, up to two more | 15 each |
  | It set off at least 5 signals, or at least 20 | 10, or 20 |
  | A program banned the address | 20 |
  | At least 3 other addresses are involved | 10 |

  It is capped at 100 and called **low** below 35, **medium** from 35 and **high** from 65.
  One program's single medium alert is therefore low; the same alert seen by a second program
  and followed by a ban is high. The points are a judgement, written in one place
  (`backend/app/incidents/rules.py`) so that they can be argued with.
- **What you can say about it.** An incident is *open*, *investigating*, *resolved* or
  *dismissed*, which you set with `PATCH /api/incidents/{id}` (each change is in the
  [activity log](security.md)). A resolved incident is over: a later signal about the same
  subject starts a new one. An investigating or dismissed one keeps taking signals and keeps its
  status.
- **Where to read them.** `GET /api/incidents` lists them, newest activity first, and can be
  narrowed by `status` (repeat it for several), `min_severity`, `min_confidence`, `address`
  and `since`. `GET /api/incidents/{id}` has the reasons, the timeline, the devices on your
  network behind its addresses and the firewall's blocks. Pages for them come next.
- **When they appear.** A run every 30 seconds files the signals that were stored at least 30
  seconds ago, so a new attack is an incident within about a minute of its first alert. The first
  run looks back 24 hours. Signals the collectors stored out of order are filed in the order
  they happened.
- **How much room they take.** A few hundred bytes for an incident and about 300 for each
  signal, which is copied so that the timeline outlives the event. An incident lists at most its
  first 1000 signals and names at most 50 addresses; it goes on counting and updating its
  severity beyond that. A home network is a few incidents a day.
- **How long they're kept.** Until you remove them: there is no retention period for incidents
  yet.
- **Pausing it.** Turning collecting off (`ARESGATE_COLLECTORS_ENABLED=false`) pauses filing too:
  nothing new is stored, so there is nothing to file.

### Reading the logs

The API writes one JSON object per line: the `time`, the `level`, the `logger`, the `message`,
the `request_id` of the request it was serving, and anything else that was logged with it. Every
request gets one `aresgate.request` line with its `method`, `path`, `status` and `duration_ms`.
The query string is left out of it, since it can carry things that shouldn't be kept.

nginx gives each request an ID too, and writes it at the end of its own access line, so one
request can be followed from nginx into the API:

```sh
make logs | grep 3f9c1e0d5b7a4c68a2e1d4f60b9a7c35
```

The ID is also sent back in the `X-Request-ID` header, so a failed request in the browser's
network tools tells you what to look for. nginx replaces any `X-Request-ID` a client sends, so
the ID is always one AresGate made.

Set these in `.env` (see `.env.example`):

| Variable | Default | What it does |
| --- | --- | --- |
| `ARESGATE_LOG_FORMAT` | `json` | `json`, or `text` for plain lines that are easier to read |
| `ARESGATE_LOG_LEVEL` | `info` | `debug`, `info`, `warning` or `error` |

Secrets are blanked out before anything is written (see
[Security](security.md#how-it-is-hardened-today)). That is a safety net: if you find one in a log,
please [report it](../SECURITY.md).

## The dashboard

The first page of the web app, for the last 24 hours or the last 7 days (the buttons at the top
right), each compared with the same length of time before it. From the top:

- **A sentence on whether anything needs you.** *Needs your attention* when there was a high or
  critical alert, *Worth a look* for medium alerts, and *All quiet* otherwise. It never says
  quiet while collectors are failing or the worker has stopped, because a network nobody is
  watching is quiet too: it says *Some sources aren't reporting* and links to the Status page.
  With nothing connected at all it asks you to connect an integration. Until AresGate has
  learned what is normal on your network this goes by how serious the alerts are.
- **Four numbers**: alerts, connections the firewall refused, devices first seen in that time
  (out of all it knows), and how the collectors are doing. The first two show how they changed
  and a small line of how they went through the day or week.
- **Network traffic** of one OPNsense interface (the busiest first, the others in a menu), in
  bits a second received and sent. It is worked out from the bytes the firewall counts, over
  15 minutes (or an hour for the week). Where the firewall wasn't read, or restarted and began
  counting again, the line has a gap rather than a made-up speed.
- **Alerts by severity** for each hour (or six hours), the **addresses refused most**, and the
  **latest alerts** with who reported each. Every chart can be shown as a table.

The page asks again every 30 seconds while it is open and in view, and when you come back to its
tab after longer than that. If a refresh fails it keeps what it has and says so. The numbers
come from `GET /api/dashboard?window=24h` (or `7d`), for someone signed in.

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
- **What happened, and when.** Every sign-in, wrong guess and sign-out is in the audit log
  ([Security](security.md)). It keeps a year of events; change that with
  `ARESGATE_AUDIT_RETENTION_DAYS` (1 to 3650) in `.env`, then `make up` or `make restart`. The API
  deletes older events when it starts and every six hours after that.
- **What an integration was asked.** Each integration's page has an API log of every request
  AresGate made to it, without secrets or query strings. It keeps 30 days; change that with
  `ARESGATE_API_LOG_RETENTION_DAYS` (1 to 3650) in `.env`, then `make up` or `make restart`
  ([Integrations](integrations.md)).
- **Adding the second step.** In Settings, on the Account page, Two-step verification, choose
  *Add an authenticator app*. Scan the QR code with the app (or open the link on the same device,
  or type in the key), enter the code it shows, and save the ten recovery codes: they are shown
  once. The same card makes new recovery codes and turns the step off. Both ask for a code from
  the app or a recovery code, and turning it off asks for the password too.
- **Changing the password, and ending sign-ins.** In Settings, on the Account page, Password asks
  for the current password and the new one twice. Changing it signs every other browser out, so
  anyone who had the old one is out; this browser stays signed in. If you think someone else is
  signed in, the Sign-ins page lists each browser with where it was and when it was last active,
  and signs one (or all but this one) out. A forgotten password can't be reset from the web app:
  see *Forgot the password* below.
- **Adding a passkey.** In Settings, on the Account page, Passkeys, choose *Add a passkey*, give
  it a name, enter your password, and unlock the device when the browser asks. Then *Sign in with a
  passkey* on the sign-in page needs nothing typed. A passkey takes the place of the password and
  the authenticator app, so it asks for no code. Remove one from the same card (it asks for the
  password); the device keeps its copy, which you can delete in its own settings.
- **A passkey won't work.** A passkey belongs to the server name, so it only works when you
  browse to `ARESGATE_SERVER_NAME` exactly as it is in `.env`: not an IP address, not another
  name that points at the same server, and not after changing the name, which makes every
  passkey useless (remove them and add them again; the password signs in meanwhile). Browsers
  also want HTTPS, which is why the page can't be reached over plain HTTP. If the browser says
  it can't make a passkey, use a recent Chrome, Edge, Firefox or Safari.
- **Lost the phone and the recovery codes.** An account with an authenticator app can't finish
  signing in without a code from it or a recovery code. If you have neither, turn the second
  step off from the machine that runs AresGate, then sign in with the password and add the app
  again:

  ```sh
  make two-factor-off ACCOUNT=<username>
  ```

  This removes the app's key and the recovery codes, ends every sign-in the account has, and
  records an event in the audit log. The same applies if AresGate was restored with a different
  app secret key than the one that encrypted the app's key: the key can't be opened, the
  sign-in fails with an error in `make logs`, and turning the step off is the way out.
- **Forgot the password.** Settings changes a password you know, but nothing in the web app
  resets one you don't yet. To start over without losing anything else, delete the account
  (which also removes its authenticator app and recovery codes) and set up again:

  ```sh
  make psql
  DELETE FROM users;
  \q
  make restart
  ```

  Then follow the setup steps with the code in `make logs`. Anyone who can run these commands
  can already read everything on the server, so this opens nothing new. The audit log keeps its
  events, including those of the account you deleted.

## Certificates

[Quick start](quick-start.md#certificates) covers getting one. After a certificate in `certs/`
changes, whether `make cert-renew` replaced it or you did, `make cert-reload` makes AresGate use
it with no restart: nginx reloads, finishes the requests it is in the middle of, and the people
signed in stay signed in. (`make restart` also works, and drops them for a moment.)

AresGate checks a certificate before it replaces the one it is serving, and refuses one that has
expired, is for another name than `ARESGATE_SERVER_NAME`, doesn't match its private key, or whose
key needs a password. The reload says which, and the old certificate keeps being served.

| What you see | What it means |
| --- | --- |
| `make cert-renew` says there is no certificate to renew | `make cert` hasn't succeeded yet for this `ARESGATE_SERVER_NAME`. Run it first |
| The reload says the certificate isn't for your server name | Either `certs/` still has the certificate for an older name (run `make cert`), or you changed `ARESGATE_SERVER_NAME` in `.env` and the running container still has the old one: `make up` applies it, and starts with the certificate in `certs/` |
| `make cert` waits for the DNS record, then gives up | The DNS server it uses can't see your public records. Set `ARESGATE_ACME_RESOLVERS` ([Quick start](quick-start.md#getting-a-lets-encrypt-certificate-ionos-dns)). Or the IONOS key can't change that domain's DNS: check it in the IONOS portal, and that the domain's DNS is hosted at IONOS |
| `make ps` says unhealthy, and the log is quiet | The certificate has expired or is for another name. Renew it, then `make cert-reload` |

To use another IONOS API key, delete `acme/ionos-api-key` and run `make cert-renew` (or
`make cert`); it asks for the new one.

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
