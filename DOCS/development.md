# Development

## What you need

- Docker with Compose, and `make`.
- [uv](https://docs.astral.sh/uv/) for the Python side. It installs the Python version in
  `.python-version`.
- Node.js 24 (22.18 or newer works) for the web app.

```sh
make install     # Python and Node dependencies, and the browser for the Playwright tests
make             # lists every command
```

## How the code is laid out

| Folder | What is in it |
| --- | --- |
| `backend/app` | The API (FastAPI), its settings and database models, `app/collectors`, which the worker (`python -m app.worker`) runs on a schedule, `app/events` and `app/metrics`, where the events and the numbers they read are stored, and `app/incidents`, which groups the events into incidents |
| `backend/migrations` | Database migrations (Alembic) |
| `backend/tests` | The API's tests (pytest) |
| `backend/e2e` | The test server's harness, used only by the end-to-end tests (see [frontend/e2e/README.md](../frontend/e2e/README.md)) |
| `frontend/src` | The web app (Vue 3, Vuetify, TypeScript), with its unit tests (Vitest) |
| `frontend/e2e` | The end-to-end tests (Playwright) |
| `docker` | What runs inside the container: the entrypoint, nginx and supervisord settings, and the certificate scripts |
| `scripts` | What runs on the host behind `make` commands (`make cert` and its siblings) |
| `.github` | The CI, CodeQL, zizmor and release workflows, and the scripts they run |
| `DOCS` | These guides |

AresGate ships as one container, and the `Dockerfile` has a stage for each purpose: `runtime`
(the production image and the default), `dev` (live reload) and `e2e` (the production image
plus the test harness, used only for tests).

## Running it while you work

- `make dev` runs the container with live reload, with your source mounted in. Open
  `https://localhost` as with `make up`. `make logs` shows the setup code on a fresh database.
- Or run the pieces on this computer: `make dev-api` (needs `ARESGATE_DATABASE_URL` pointing at
  a Postgres, and makes a throwaway app secret key unless `ARESGATE_SECRET_KEY` is set, so
  anything it encrypts can't be read after you stop it) and `make dev-web`, which serves the web
  app on `http://127.0.0.1:5173` and passes `/api` to the API (browse to `http://localhost:5173`
  to try passkeys, which can't be made for an IP address). On an empty database, run
  `uv run alembic upgrade head` in `backend/` first, and
  `uv run python -c 'from app.security.setup_code import announce; announce()'` to print a setup
  code. Outside production the API also accepts changes from pages on `http://localhost` and
  `http://127.0.0.1`, which is where the dev server runs.

## Checks

Every command is the same one CI runs, so a failure in CI can be reproduced locally.

| Command | What it does |
| --- | --- |
| `make test` | pytest (on a throwaway Postgres) and Vitest, with coverage |
| `make e2e` | The Playwright tests against the test container; `make e2e-host` runs them with no container |
| `make lint` | ruff, pyright (strict) and bandit; ESLint, Prettier and vue-tsc; hadolint, ShellCheck, actionlint and a check that no script ends a pipeline in `grep --quiet` |
| `make format` | Fixes formatting and the lint problems that can be fixed automatically |
| `make audit` | pip-audit and npm audit |
| `make scan` | Trivy on the source and on the built image |

### Coverage

The target is **100%** for pytest and Vitest, and the build fails below **95%** so that one
hard-to-reach line doesn't block a change. The Playwright specs have more leeway: their coverage
is reported and never fails the build, and the web app's is kept above **90%**. A pull request
that adds code adds the tests for it in all three.

SonarQube Cloud must report **zero open issues** on the pull request.

## Making a change

1. Every change has a ticket with a key like `AR-12` (open an issue and a maintainer will make
   the ticket). Create the branch `AR-12-short-name` from `master`.
2. Start every commit message and the pull request's title with the key: `AR-12 Add the README`.
3. Mention only that ticket's key in the title, commits and description. To refer to another
   ticket, write "ticket 12", because automation reads the keys it finds.
4. Open a pull request using the template and keep the branch linear: rebase on `master`, don't
   merge `master` into your branch.
5. When CI is green and a maintainer has reviewed it, the maintainer merges it by rebasing.
   Rebasing keeps the history in a straight line, so there are no merge commits.

[CONTRIBUTING.md](../CONTRIBUTING.md) has the short version.

## Database migrations

`cd backend && uv run alembic revision --autogenerate --rev-id 000n -m "what changed"` writes a
migration from the models; read it and fix what autogenerate gets wrong (such as a column type
it imports from the app). CI applies every migration, checks that the models and the migrations
agree, goes down to nothing and up again, and then applies the newest migration a second time to
a database that already has it, which must change nothing. So a migration creates with
`if_not_exists=True` and drops with `if_exists=True`, as the existing ones do. SQL that has no
such option, such as a trigger, drops what it makes (`DROP TRIGGER IF EXISTS`) before making it.

The audit log's table refuses `UPDATE` and `DELETE` with a trigger (`app/models/audit.py`), which
the tests make through the models and the migration makes with its own copy of the SQL. Code that
has to empty the tables, such as a test's cleanup or the end-to-end harness, calls
`audit.allow_deletes(session)` first, in the same transaction.

## Storing events from a collector

A collector that reads events makes a `NewEvent` (`app/events/event.py`) for each and hands them
to `await context.record(events)`, which stores the ones that aren't stored yet and returns how
many were new, for the run's item count.

- `source` and `connection` are the integration's and the connection's keys, and `kind` is one
  lowercase word (`alert`, `firewall`, `authentication`). They are the collector's own words and
  are checked; everything else came from the other system and is cleaned on the way in: control
  characters in text become spaces, what isn't an address or a port is dropped without losing
  the event, and a record the database would refuse (NUL characters, NaN) is made acceptable.
- `identity` is what makes it this event at the source: its id there, or else the facts that
  together can't be anyone else's. Its hash and the event's time are the key that stops an event
  read twice from being stored twice, so it must not hold anything that changes between reads.
- `severity` is `Severity.INFO` to `Severity.CRITICAL`, which the web app shows as info, low,
  medium, high and critical.
- An event that has no time of its own, such as a CrowdSec decision, is dated with the run's
  `context.now` and handed to `await context.record_unseen(events)` instead. The unique index
  holds the time, so the same state read by a later run would be stored again by `record`;
  `record_unseen` first looks for the identity among the source's events kept within its
  retention and stores only the ones it hasn't seen.
- The table is partitioned by week of `occurred_at` (`app/partitions.py`), made on demand
  under an advisory lock that the retention purge takes too, so a purge never drops a week an
  event is being written into. That is why the primary key and the unique index both hold the
  time, and why a foreign key to an event would need the time as well. Alembic is told to leave
  the partitions out (`migrations/env.py`), so `alembic check` and autogenerate don't ask for
  them to be dropped. Tests that store events get a clean set of partitions from the `session`
  fixture.

## Storing samples from a collector

A collector that reads numbers makes a `NewSample` (`app/metrics/sample.py`) for each and hands
them to `await context.record_samples(samples)`, which stores the ones that aren't stored yet
and returns how many were new.

- `source` and `connection` are the integration's and the connection's keys, `name` is what is
  measured in lowercase words joined by dots or underscores (`system.load_1m`,
  `interface.bytes_in`), and `labels` (at most eight) tell one series from another of the same
  name, such as `{"interface": "igc0"}`. The names are the collector's own and are checked; a
  label's value came from the other system and is cleaned on the way in. Keep a label to
  something with a few values: each different set of labels is a series of its own.
- A series (`metric_series`) is made the first time one of its samples is stored, and goes when
  its last sample does, so the samples (`metric_samples`) hold only the series' number, the time
  and the value. The same series at the same moment is stored once.
- The samples are partitioned by week of `sampled_at` and kept the same way as events, with the
  same code: `app/partitions.py` makes and drops the weeks, and `app/retained.py` holds how long
  each source keeps its rows and purges what is past it. A table that uses them says which
  columns hold the time and the source, and what to run after a purge (`app/metrics/retention.py`
  forgets the series left without samples).

## Storing devices from a collector

A collector that lists the devices on the network makes a `NewSighting` for each with
`NewSighting.of(mac, seen_at, address=..., hostname=..., vendor=...)` (`app/devices/sighting.py`)
and hands them to `await context.record_devices(sightings)`, which returns how many different
devices there were.

- `of` returns `None` for a hardware address that isn't a device's (not six bytes, all zeros, or
  with the multicast bit set, as the broadcast address has), and takes the address in any of the
  forms programs write it, including FreeBSD's without leading zeros (`0:c:29:a:b:c`). The IP
  address, host name and maker came from the other system: an address that isn't one, and a name
  that stands for none (`*`, `?`, `-`), are left out without costing the device, and text is
  cleaned and cut to fit.
- A device (`devices`) is told apart by its MAC address, and `app/devices/store.py` updates it
  when it is listed again: the times only widen (first seen moves back and last seen moves
  forward), a name or maker replaces the one kept and none leaves it, and an address is added to
  the device's rows (`device_addresses`). Sightings of one device in the same call are taken
  together, and a time ahead of now is taken as now.
- The OPNsense lease searches share `app/collectors/opnsense/leases.py`: a collector for another
  DHCP server only needs its path and what makes a lease current.

## Incidents

`app/incidents` groups the events of every integration into incidents, with no AI. The worker
runs `app/incidents/run.py` every 30 seconds beside the collectors; it calls
`engine.correlate(db, now)`, which reads the events stored since the last run (the cursor is
`system_info.incidents.cursor`), files each in the order it happened and saves the cursor with
the incidents, so a run that fails is read again. An advisory lock keeps two runs from
overlapping.

- **What is a signal** is `engine.KINDS` (`alert`, `decision`) at `engine.MIN_SEVERITY` or more.
  A collector's new kind of event is not one until it is added there, with a test.
- **What it is about** is `subject.subject_of`: the address of interest, or `rule:<source>:<rule>`
  for a signal that names none. Changing it changes which incidents later signals join, not
  the ones filed.
- **Episodes** are `episode.py`: what makes signals one incident. `activity_of` reads a signal's
  signature and summary as a scan or a brute force, `gap_of` is how long the quiet may be for
  it, `block_of` is the /24 or /64 that its neighbours share (none for a private address),
  `MAX_SPAN` ends an incident after a day, and `waves_of`, `with_ports` and `explain` build what
  an incident says about its own grouping. `engine._current` looks for the incident of the same
  subject, then of the same block for the activities in `episode.GROUPED`, and
  `engine._consolidate` merges incidents that turn out to be one episode. To group another kind
  of activity, add its patterns and gap there, add it to `GROUPED` and cover it in
  `tests/test_incidents_episode.py`. The e2e factory takes `scan`, `neighbours`, `waves` and
  `ports` to make a sweep.
- **How sure** is `rules.assess`: a list of `Reason(rule, points, text)` that is stored on the
  incident (`incidents.reasons`) next to the confidence it adds up to. To add a rule, add its
  reason there, give `Facts` what it needs (an incident keeps the totals it needs, so scoring
  never reads old signals) and add a case to `tests/test_incidents_rules.py`. A rule needs a
  sentence a person can read: nothing is scored that can't be explained.
- **What is stored** is `incidents` (a summary that grows with each signal) and
  `incident_signals` (the timeline, copied from the events, which expire sooner).
- **Verdicts** are `verdict_rules` (see `models/verdicts.py`), matched by
  `incidents/verdicts.py`: `judge(signal, rules)` returns the rule that decides, the most
  specific first and then the strongest. `engine._absorb` is the one place a signal changes an
  incident's summary, for a new one (`_join`) and for `reapply`, which the API calls in the
  same transaction as a change to a rule and which builds each incident that is not resolved
  again from its stored signals. A signal called not suspicious or low priority only changes the
  counts and the times; `rules.assess` leaves it out and a threat is worth 100. A new thing the
  analyst or the alert engine does with a verdict reads `incidents.verdict` and the counts, not
  the rules.
- **The API** is `app/api/incidents.py`, with the queries in `app/incidents/queries.py` so that
  the AI analyst can call them too. They only read, apart from the status.
- **Changes to many** are `incidents/bulk.py`: `set_status` and `give_verdict` work out a change
  the same way whether `apply` is set or it is only asked about, so a preview is what it then
  does, and `take_back` undoes one from the `undo` a change returned. The API commits one
  transaction for a change, with one audit entry, and holds the engine's advisory lock for a
  verdict. The scope of a verdict (`scope_of`) is the same as the web app's: the subject address,
  else the first alert of an incident that has a signature. `queries.conditions` is what the list
  and a change to `matching` share, so they can never disagree about which incidents they mean.
- **Search** is a shared language, `app/querylang.py`, with a set of fields for each place that
  searches: `incidents/search.py` for the incidents and `events/search.py` for the logs.
  `parse(text, context)` turns the words of the search box
  into terms, each with a condition, a label for the chip and its place in the text, or raises
  `SearchError` with a message for the person who typed it (the API answers 422 with it).
  Nothing a person types is put into SQL as anything but a bound value, the text is limited
  (500 characters, 12 terms, 8 choices, 100 characters a word) and the API sets a 5 second
  `statement_timeout` for the request, so a search can't hold the database up. To add a field,
  write a compiler `(Clause, Context) -> (condition, label)`, add it to `FIELDS` (and
  `ALIASES`, if it has a short name), and add a case to `tests/test_incidents_search.py` (or
  `tests/test_events_search.py`) that runs it against rows, and a line to the list of ways to
  search in `frontend/src/search.ts`.
  `queries.search` takes the conditions as `extra`, and answers with `facets` (the counts per
  severity and integration of everything found, not of the page).
- **The logs** are `api/logs.py`, with the queries in `events/queries.py` (so the AI analyst can
  call them too). A page is found again by a cursor, `"<microseconds>.<id>"`, of the last event on
  it: the events table is partitioned by week and its key is `(occurred_at, id)`, so paging by
  that never reads more than one page. The summary (the counts and the chart) is of the newest
  50,000 matches; an export is capped at the same and is streamed, with a longer
  `statement_timeout`. The Playwright harness makes events with `POST /api/__test__/factories/events`
  (`harness.createEvents()`), which are not filed into incidents.
- **Tests** build events with `tests.helpers.new_event`, store them with `record_events` and
  run the engine at a time of their choosing. Use a public address for an attacker
  (`93.184.216.34`): the documentation ranges are not global addresses.

## Dependencies

Add the newest version of a dependency unless there's a reason not to, and prefer packages that
are still being developed. Python dependencies are locked in `backend/uv.lock` and installed as
prebuilt wheels only, and npm dependencies in `frontend/package-lock.json` are installed without
running their scripts. Dependabot opens pull requests for new versions.
