import type { Page } from '@playwright/test'

import { expect, test } from '../support'

/** When each request the page made on opening started and was answered, in milliseconds from the
 * moment the page was asked for. */
interface Timings {
  [name: string]: { start: number; end?: number }
}

function watch(page: Page, names: Record<string, RegExp>): { at: Timings; began: number } {
  const at: Timings = {}
  const began = Date.now()
  const nameOf = (url: string) => Object.keys(names).find((name) => names[name]?.test(url))
  page.on('request', (request) => {
    const name = nameOf(request.url())
    if (name && !at[name]) at[name] = { start: Date.now() - began }
  })
  page.on('requestfinished', (request) => {
    const name = nameOf(request.url())
    const found = name ? at[name] : undefined
    if (found && found.end === undefined) found.end = Date.now() - began
  })
  return { at, began }
}

/** What opening AresGate waits for before the first page: who is signed in, and the page's own
 * code and numbers. None of these depend on each other, so none should wait for another. */
test.describe('opening the app', () => {
  test('asks whether there is an account and who is signed in at the same time', async ({
    dashboard,
    page,
  }, testInfo) => {
    // The first answer is held back, so a second request that waited for it would start late.
    await page.route('**/api/setup/status', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 400))
      await route.continue()
    })
    const { at } = watch(page, {
      setup: /\/api\/setup\/status$/,
      session: /\/api\/auth\/session$/,
    })

    await dashboard.goto()
    await expect(dashboard.heading).toBeVisible()

    const { setup, session } = at
    expect(setup).toBeDefined()
    expect(session).toBeDefined()
    expect(Math.abs((session?.start ?? 0) - (setup?.start ?? 0))).toBeLessThan(200)
    await testInfo.attach('startup-timings', {
      body: JSON.stringify(at, null, 2),
      contentType: 'application/json',
    })
  })

  test('asks for the dashboard’s numbers while the page’s code is still on its way', async ({
    dashboard,
    page,
  }, testInfo) => {
    const delay = 1500
    let chunkAnswered = 0
    await page.route(/\/static\/DashboardView-[^/]*\.js$/, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, delay))
      chunkAnswered = Date.now()
      await route.continue()
    })
    const { at, began } = watch(page, {
      chunk: /\/static\/DashboardView-[^/]*\.js$/,
      dashboard: /\/api\/dashboard\?window=24h$/,
      collectors: /\/api\/collectors(\?.*)?$/,
    })
    let dashboardRequests = 0
    page.on('request', (request) => {
      if (/\/api\/dashboard\?window=24h$/.test(request.url())) dashboardRequests += 1
    })

    await dashboard.goto()
    await expect(dashboard.heading).toBeVisible()

    const { chunk, dashboard: numbers } = at
    expect(chunk).toBeDefined()
    expect(numbers).toBeDefined()
    // The numbers were asked for long before the page's code was let through, and the page did
    // not ask for them a second time when it arrived.
    expect((numbers?.start ?? Infinity) + began).toBeLessThan(chunkAnswered)
    expect(dashboardRequests).toBe(1)
    await testInfo.attach('startup-timings', {
      body: JSON.stringify(at, null, 2),
      contentType: 'application/json',
    })
  })
})
