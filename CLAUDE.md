# AresGate

A self-hosted, open-source home-network security platform: an AI "SOC analyst" that watches the
network through OPNsense, ntopng and Wazuh (Suricata and CrowdSec later). One container: nginx
(TLS 1.3), a FastAPI API, PostgreSQL 18 and a Vue 3 web app, built on Chainguard's Wolfi. It is
public, so keep the code, docs and defaults generic: the maintainer's own domain and registry
are examples, never assumptions. [DOCS/development.md](DOCS/development.md) has the layout and
every command (`make` lists them).

## Stack

- `backend/`: Python 3.14, FastAPI, SQLAlchemy and Alembic, uv. pyright strict, ruff, bandit.
- `frontend/`: Vue 3, Vuetify 4, TypeScript 6 (pinned: 7 breaks typescript-eslint), Vite, Pinia.
  ESLint, Prettier, vue-tsc.
- PostgreSQL listens on a unix socket only, with peer authentication: there is no database
  password, on purpose (Sonar's `python:S2115` is ignored for that file).
- Tests: pytest (on Postgres), Vitest, Playwright against the e2e image or `make e2e-host`.

## Rules

- **Tickets.** Branch `AR-n-short-name`, commits `AR-n Message`, PR title starts with `AR-n`.
  Jira automation moves tickets from the PR text: it sets In Progress when a branch is created
  and Done when the PR merges. Mention only the PR's own key anywhere in a title, commit or
  description. To refer to another ticket write "ticket 12", never `AR-12` or `AR 12`. Don't
  move tickets by hand unless asked.
- **History.** Rebase merges only, never merge commits. Keep a branch linear: rebase onto
  `master` (`git rebase --onto origin/master <old-base> <branch>`), never merge `master` into it,
  and push with `--force-with-lease` and only on your own branches. The maintainer merges.
- **Coverage.** Aim for 100% in pytest and Vitest, with the failure threshold at 95%. The
  Playwright specs have more leeway: their coverage is reported and never fails the build, and
  stays above 90%. A change that adds code adds its tests in all three.
- **Sonar.** Zero open SonarQube issues; CI fails any pull request with one. Known rules it
  enforces: `uv run`, `uv sync` and `uvx` take `--no-build` (shell:S8541); shell scripts send
  error messages to stderr (S7677).
- **Pull requests.** Follow `.github/pull_request_template.md`. Never leave an unchecked
  `- [ ]` box in a description (GitHub shows it as incomplete work): say what CI will still check
  in prose instead. Fill in what you ran and what you could not run.
- **CI.** Workflows pin every action by full commit SHA and are audited by zizmor, so look up the
  SHA of a release when you add an action, and give each job only the permissions it needs.
  A workflow that publishes uses no build cache.
- **Releases.** Versions start at 0.0.1. Never bump a version or create a tag or release unless
  asked: the maintainer publishes releases ([DOCS/releasing.md](DOCS/releasing.md)).
- **Dependencies.** The newest version unless there's a reason, preferring maintained packages.
  Python wheels only and npm without install scripts, so installing never runs a dependency's
  code. Python 3.14.8 and PostgreSQL 18 and TypeScript 6.0.3 are the maintainer's pins.

## Design notes

- The Playwright test harness (`backend/e2e`, served under `/api/__test__`) can erase the
  database. It exists only in the Dockerfile's `e2e` target and `make e2e-host`; the app factory
  refuses to start without `ARESGATE_ENVIRONMENT=test`, and the smoke test asserts the production
  image answers 404 there. Never copy it into the `runtime` stage.
- Build features so the AI analyst can use them as tools. The analyst is read-only at first.
  Credentials are encrypted and write-only; hosted AI providers get pseudonymized addresses.
- The base image is the public `cgr.dev/chainguard/wolfi-base`, pinned by digest. A Chainguard
  login is optional everywhere, so contributors and forks build without one.
