import { test as base } from '@playwright/test'

import { addWebCoverage, coverageEnabled } from './coverage'
import { Harness, type BaselineData } from './harness'
import { AppShell } from './pages/app-shell'
import { OverviewPage } from './pages/overview-page'

export interface AresGateFixtures {
  /** The logo and the theme switcher that every page has. */
  shell: AppShell
  overview: OverviewPage
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
