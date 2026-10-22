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
| `backend/app` | The API (FastAPI), its settings and database models |
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
| `make lint` | ruff, pyright (strict) and bandit; ESLint, Prettier and vue-tsc; hadolint, ShellCheck and actionlint |
| `make format` | Fixes formatting and the lint problems that can be fixed automatically |
| `make audit` | pip-audit and npm audit |
| `make scan` | Trivy on the source and on the built image |

### Coverage

The target is **100%** for pytest, Vitest and Playwright, and the build fails below **95%** so
that one hard-to-reach line doesn't block a change. A pull request that adds code adds the
tests that keep it at 100%.

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

## Dependencies

Add the newest version of a dependency unless there's a reason not to, and prefer packages that
are still being developed. Python dependencies are locked in `backend/uv.lock` and installed as
prebuilt wheels only, and npm dependencies in `frontend/package-lock.json` are installed without
running their scripts. Dependabot opens pull requests for new versions.
