import type { Page } from '@playwright/test'

import { expect, expectAccessible, test, waitForMotion } from '../support'

/** The pages that show the most data, as an address and a name for its screenshot. */
const PAGES = [
  { name: 'dashboard', path: '/' },
  { name: 'incidents', path: '/incidents' },
  { name: 'threats', path: '/threats' },
  { name: 'devices', path: '/devices' },
  { name: 'assets', path: '/assets' },
  { name: 'logs', path: '/logs' },
  { name: 'alerts', path: '/alerts' },
  { name: 'status', path: '/status' },
  { name: 'integrations', path: '/integrations' },
  { name: 'ai-usage', path: '/ai-usage' },
  { name: 'flow', path: '/flow' },
]

/** A phone, a tablet, a computer and a very wide wall screen. */
const SIZES = [
  { width: 360, height: 780 },
  { width: 768, height: 1024 },
  { width: 1280, height: 800 },
  { width: 2560, height: 1440 },
]

const SCHEMES = ['light', 'dark'] as const

const LAPTOP = '192.168.1.20'

async function sideways(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
}

async function arrive(page: Page, path: string): Promise<void> {
  await page.goto(path)
  await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible()
  await waitForMotion(page)
}

test.describe('every main page, at every size', () => {
  test.beforeEach(async ({ harness }) => {
    await harness.createActivity({
      collectors: ['ok'],
      alerts: { critical: 1, high: 2, medium: 3, low: 4 },
      blocked: { '203.0.113.9': 5, '198.51.100.7': 2 },
      traffic: { igc0: 80, igc1: 5 },
      devices: 2,
    })
    await harness.createAssets({
      devices: [
        {
          hostname: 'laptop',
          mac: '00:11:22:0a:0b:0c',
          addresses: [LAPTOP],
          listed: [{ source: 'opnsense', via: 'arp', minutes_ago: 1 }],
        },
      ],
    })
    await harness.createEvents([
      {
        src_address: LAPTOP,
        src_port: 51000,
        dst_address: '93.184.216.34',
        dst_port: 443,
        protocol: 'tcp',
        repeat: 4,
        seconds_ago: 300,
      },
    ])
    await harness.createIncidents([
      { address: '93.184.216.34', severity: 'critical', signals: 4, minutes_ago: 5 },
      { address: '8.8.4.10', severity: 'high', ban: true, minutes_ago: 20 },
      { address: '8.8.5.11', severity: 'medium', blocks: 3, minutes_ago: 30 },
    ])
  })

  // Not a gate on how it looks: the screenshots are attached to the report, which CI uploads,
  // for someone to open. What is asserted is that nothing makes the page scroll sideways.
  for (const size of SIZES) {
    test(`fit ${size.width} px wide, light and dark`, async ({ page }, testInfo) => {
      test.setTimeout(180_000)
      await page.setViewportSize(size)

      for (const scheme of SCHEMES) {
        await page.emulateMedia({ colorScheme: scheme })
        for (const { name, path } of PAGES) {
          await arrive(page, path)
          expect(await sideways(page), `${name} scrolls sideways`).toBeLessThanOrEqual(0)
          await testInfo.attach(`${name}-${size.width}-${scheme}`, {
            body: await page.screenshot({ fullPage: true }),
            contentType: 'image/png',
          })
        }
      }
    })
  }

  test('the pages that show data grow past 1600 px, and the forms stay a column', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 2560, height: 1440 })

    await arrive(page, '/')
    const dashboard = await page.locator('.app-page').boundingBox()
    await arrive(page, '/status')
    const status = await page.locator('.app-page').boundingBox()

    expect(dashboard?.width).toBeGreaterThan(1600)
    expect(status?.width).toBeLessThanOrEqual(1440)
  })

  test('a wall display is scaled up with the screen', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await arrive(page, '/?wall=1')
    const small = await page.locator('.dashboard--wall').evaluate((el) => getComputedStyle(el).zoom)

    await page.setViewportSize({ width: 2560, height: 1440 })
    const big = await page.locator('.dashboard--wall').evaluate((el) => getComputedStyle(el).zoom)

    expect(Number(small)).toBeGreaterThanOrEqual(1.25)
    expect(Number(big)).toBeGreaterThan(Number(small))
  })

  test('the pages read in Windows high contrast', async ({ page }) => {
    test.setTimeout(180_000)
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.emulateMedia({ forcedColors: 'active' })

    for (const { name, path } of PAGES) {
      await arrive(page, path)
      // The system chooses every color, so contrast is its to keep.
      await expectAccessible(page, { disableRules: ['color-contrast'], where: name })
      expect(await sideways(page), `${name} scrolls sideways`).toBeLessThanOrEqual(0)
    }
  })

  test('nothing keeps moving when the system asks for less motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await arrive(page, '/')

    const running = () =>
      page.evaluate(
        () =>
          document
            .getAnimations()
            .filter(
              (animation) =>
                animation.playState === 'running' &&
                animation.effect?.getComputedTiming().iterations === Infinity,
            ).length,
      )

    // A spinner that is still loading is allowed to finish and go.
    await expect.poll(running).toBe(0)
  })
})
