import { test as base, type BrowserContext, type Page } from '@playwright/test'

import { addWebCoverage, coverageEnabled } from './coverage'
import { Harness, readJson, type BaselineData } from './harness'
import { ActivityPage } from './pages/activity-page'
import { AppShell } from './pages/app-shell'
import { IntegrationPage } from './pages/integration-page'
import { IntegrationsPage } from './pages/integrations-page'
import { OverviewPage } from './pages/overview-page'
import { SecurityPage } from './pages/security-page'
import { SettingsPage } from './pages/settings-page'
import { SetupPage } from './pages/setup-page'
import { SignInPage } from './pages/sign-in-page'
import { SignInsPage } from './pages/sign-ins-page'
import { StatusPage } from './pages/status-page'
import { VirtualAuthenticator } from './virtual-authenticator'

export interface AresGateFixtures {
  /** The logo and the theme switcher that every page has. */
  shell: AppShell
  overview: OverviewPage
  integrations: IntegrationsPage
  integration: IntegrationPage
  signIn: SignInPage
  setup: SetupPage
  /** The account settings page: the password, passkeys and two-step verification. */
  security: SecurityPage
  settings: SettingsPage
  signIns: SignInsPage
  activity: ActivityPage
  status: StatusPage
  /** The passkey device every page has, which unlocks itself. Chromium only. */
  authenticator: VirtualAuthenticator
  /** Whether the page starts signed in as the baseline account, as most pages need. */
  signedIn: boolean
  /**
   * Signs in as the baseline account from another browser, with its own cookies and the user
   * agent given, and returns that browser's page. Each is closed when the test ends.
   */
  signInElsewhere: (userAgent: string) => Promise<Page>
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

  integrations: async ({ page }, use) => {
    await use(new IntegrationsPage(page))
  },

  integration: async ({ page }, use) => {
    await use(new IntegrationPage(page))
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

  settings: async ({ page }, use) => {
    await use(new SettingsPage(page))
  },

  signIns: async ({ page }, use) => {
    await use(new SignInsPage(page))
  },

  activity: async ({ page }, use) => {
    await use(new ActivityPage(page))
  },

  status: async ({ page }, use) => {
    await use(new StatusPage(page))
  },

  signInElsewhere: async ({ browser, baseURL, baseline }, use) => {
    if (!baseURL) throw new Error('playwright.config.ts needs a baseURL')
    const origin = new URL(baseURL).origin
    const contexts: BrowserContext[] = []
    await use(async (userAgent) => {
      const context = await browser.newContext({
        baseURL,
        ignoreHTTPSErrors: true,
        locale: 'en-US',
        timezoneId: 'UTC',
        userAgent,
      })
      contexts.push(context)
      const response = await context.request.post('/api/auth/login', {
        data: baseline.account,
        headers: { Origin: origin },
      })
      await readJson(response, 'Signing in from another browser')
      return context.newPage()
    })
    await Promise.all(contexts.map((context) => context.close()))
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
