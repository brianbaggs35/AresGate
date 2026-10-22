import { test as base } from '@playwright/test'

import { addWebCoverage, coverageEnabled } from './coverage'
import { Harness, readJson, type BaselineData } from './harness'
import { AppShell } from './pages/app-shell'
import { OverviewPage } from './pages/overview-page'
import { SecurityPage } from './pages/security-page'
import { SetupPage } from './pages/setup-page'
import { SignInPage } from './pages/sign-in-page'
import { VirtualAuthenticator } from './virtual-authenticator'

export interface AresGateFixtures {
  /** The logo and the theme switcher that every page has. */
  shell: AppShell
  overview: OverviewPage
  signIn: SignInPage
  setup: SetupPage
  security: SecurityPage
  /** The passkey device every page has, which unlocks itself. Chromium only. */
  authenticator: VirtualAuthenticator
  /** Whether the page starts signed in as the baseline account, as most pages need. */
  signedIn: boolean
  /** Puts the database back to the baseline before every test, so none depends on another. */
  freshDatabase: undefined
  /** Collects the web app's coverage in Chromium, for every test. */
  webCoverage: undefined
}

export interface AresGateWorkerFixtures {
  /** Calls to the test server's harness: fixtures, factories and row counts. */
  harness: Harness
  /** What the baseline holds. */
  baseline: BaselineData
}

export const test = base.extend<AresGateFixtures, AresGateWorkerFixtures>({
  harness: [
    async ({ playwright }, use, workerInfo) => {
      const { baseURL } = workerInfo.project.use
      if (!baseURL) throw new Error('playwright.config.ts needs a baseURL')
      const harness = await Harness.connect(baseURL, playwright.request)
      await use(harness)
      await harness.dispose()
    },
    { scope: 'worker' },
  ],

  baseline: [
    async ({ harness }, use) => {
      await use(await harness.describe())
    },
    { scope: 'worker' },
  ],

  freshDatabase: [
    async ({ harness }, use) => {
      await harness.clean()
      await use(undefined)
    },
    { auto: true },
  ],

  shell: async ({ page }, use) => {
    await use(new AppShell(page))
  },

  overview: async ({ page }, use) => {
    await use(new OverviewPage(page))
  },

  signIn: async ({ page }, use) => {
    await use(new SignInPage(page))
  },

  setup: async ({ page }, use) => {
    await use(new SetupPage(page))
  },

  security: async ({ page }, use) => {
    await use(new SecurityPage(page))
  },

  // Automatic, because without a device to answer, a browser with nobody at it waits for a
  // security key to be plugged in, and a test that asks for a passkey hangs.
  authenticator: [
    async ({ page }, use) => {
      const authenticator = await VirtualAuthenticator.attach(page)
      await use(authenticator)
      await authenticator.detach().catch(() => {
        // The page may have gone first, taking the device with it.
      })
    },
    { auto: true },
  ],

  signedIn: [true, { option: true }],

  // The sign-in is done through the API, which is quicker than the form, and the form has its
  // own tests. The cookie goes to the page's browser context. Cleaning the database ends every
  // sign-in, so this relies on Playwright setting up automatic fixtures such as `freshDatabase`
  // before the ones a test asks for.
  page: async ({ page, baseURL, baseline, signedIn }, use) => {
    if (signedIn) {
      if (!baseURL) throw new Error('playwright.config.ts needs a baseURL')
      const response = await page.context().request.post('/api/auth/login', {
        data: baseline.account,
        // What a browser sends, which the API checks on every change.
        headers: { Origin: new URL(baseURL).origin },
      })
      await readJson(response, 'Signing in')
    }
    await use(page)
  },

  webCoverage: [
    async ({ page, browserName }, use) => {
      // Chromium is the only browser that reports coverage.
      const collect = browserName === 'chromium' && coverageEnabled()
      if (collect) await page.coverage.startJSCoverage({ resetOnNavigation: false })
      await use(undefined)
      if (collect) await addWebCoverage(await page.coverage.stopJSCoverage())
    },
    { auto: true },
  ],
})

export { expect } from '@playwright/test'
