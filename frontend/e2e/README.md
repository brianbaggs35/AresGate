# End-to-end tests

Playwright drives the real app in Chromium, on a computer-sized screen (`desktop`) and a phone
(`mobile`, a Pixel 7). Every test starts from the same **baseline** data, so you always know what
is in the database.

The specs run against a test server in one of two ways, and CI runs both:

- **In the container** (`make e2e`): the Dockerfile's `e2e` target is the production image plus
  the test harness, so nginx, TLS and the image are part of what is tested. It listens on
  `https://localhost:9443`, with throwaway data in memory.
- **On this computer** (`make e2e-host`): the API (with the harness) and the built web app run
  straight on your machine, on a throwaway Postgres, with no container. A failure that only
  shows up in one of the two points at the container, or at the code.

## Running them

```sh
make install           # once: dependencies and Playwright's Chromium
make e2e               # build and start the test container, then run every spec
make e2e ARGS="overview --project=mobile"   # just some of them
make e2e-host          # the same specs, with no container
make e2e-up            # keep the test container running (with the baseline loaded) ...
make e2e-ui            # ... and write specs in Playwright's UI,
make e2e-codegen       # ... or record one by clicking through the app
make e2e-report        # open the last run's HTML report
make e2e-coverage      # check the last full run's coverage reached its minimum
make e2e-down          # stop the container and throw its data away
```

`ARESGATE_E2E_URL` points the tests at another test server. `ARESGATE_E2E_BROWSER` uses a Chromium
you already have, and `ARESGATE_E2E_VIDEO=off` skips the videos of failed tests (they need
Playwright's ffmpeg).

## Writing a spec

Specs live in `e2e/specs`. `*.mobile.spec.ts` only runs on the phone and `*.desktop.spec.ts` only
on the computer. A spec for another size sets it for a group of tests with
`test.use({ viewport: { width: 768, height: 1024 } })`, as `layout.desktop.spec.ts` does for a
tablet. Import from `../support`:

```ts
import { expect, test } from '../support'

test('shows that the API is up', async ({ overview }) => {
  await overview.goto()
  await expect(overview.apiStatus).toHaveText('API: Running')
})
```

- The web app marks what tests look for with `data-test="…"`; `getByTestId()` reads it. Prefer
  roles and visible text (`getByRole`, `getByText`) where they say what a person sees.
- **Page objects** (`support/pages`) hold the locators for a page, and are fixtures: add one to
  `support/test.ts` and `support/index.ts` for each new page.
- The `shell` fixture (`AppShell`) is what surrounds every page: the logo, the menu (at the side,
  or at the bottom on a phone), the page's title and the theme switcher. A page that belongs in
  the menu is added to `src/navigation.ts`; keep it to five, which is all a phone's bar holds.
- **Every test starts from the baseline.** The `freshDatabase` fixture cleans the database
  before each test, so no test depends on another.
- **Every `page` starts signed in** as the baseline account, through the API, since most pages
  need it. A spec or group of specs for what comes before that turns it off with
  `test.use({ signedIn: false })` and uses the `signIn` and `setup` page objects. Cleaning the
  database ends every sign-in, so a test can also use `harness.clean()` to end its own.
- **`harness`** is the test server's harness (`backend/e2e`, served under `/api/__test__`, only by
  the e2e image and `make e2e-host`): `clean()`, `loadFixture(name)`, `createSystemInfo()`,
  `createAccount()` and other factories, `rowCounts()` and `describe()` for what the baseline
  holds, which includes the account to sign in with (`baseline.account`). The `fresh-install`
  state has no account and waits for the setup code in `baseline.fresh_install_setup_code`. A new
  table gets a
  factory in `backend/e2e/factories.py` and an endpoint in `backend/e2e/api.py`, so specs can make
  records on demand; give the baseline the rows every spec can rely on in `baseline.py`.
- **`authenticator`** is the passkey device every page has, made of software (Chromium's virtual
  authenticator, `support/virtual-authenticator.ts`). It unlocks itself, so a test adds a passkey
  and signs in with it without a prompt to click through, and `setUnlockable(false)` makes it
  refuse. Ask for it to see what the device holds. A passkey
  belongs to a server name, which is why `make e2e-host` serves the web app at
  `http://localhost:…` and not at the IP address that means the same.
- `expectAccessible(page)` runs axe against WCAG 2.2 A and AA. Check each new page in both themes.
- Tests run one at a time per shard, since they share one database.

## Coverage

The aim is 100% of the web app's source and the API's, with a minimum of 95%, as for the unit
tests.

- The web app's coverage comes from Chromium and is mapped back to `src/` through the test
  build's inline source maps. `npm run e2e:coverage` merges the raw data of one run, or of every
  shard and both servers in CI, and fails below the minimum for lines, statements and functions
  (`ARESGATE_E2E_COVERAGE_MIN`, 95 by default). Branches are reported only, because a few
  defensive ones can only be reached by a unit test.
- The API runs under coverage.py, and the report (`GET /api/__test__/coverage`) is saved with
  the rest in `e2e-results/coverage`. It is not held to a minimum: the unit tests do that, and some
  of the API is only used by features that don't exist yet.

Set `ARESGATE_E2E_COVERAGE=off` to skip collecting coverage while debugging a spec.

## In CI

`End-to-end in the container` and `End-to-end on the runner` each run the specs in two shards;
`End-to-end coverage` merges all four shards' web coverage and holds it to the minimum. Each
shard uploads its HTML report, and traces, screenshots and videos of failures, as an artifact.
