import { expect, expectAccessible, test } from '../support'

const BUSY = {
  collectors: ['ok' as const],
  alerts: { critical: 1, high: 1, medium: 2, low: 1 },
  blocked: { '203.0.113.9': 5, '198.51.100.7': 2 },
  traffic: { igc0: 80, igc1: 5 },
  devices: 2,
}

test.describe('charts you can act on', () => {
  test.beforeEach(async ({ harness, dashboard }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()
  })

  test('opens the blocks from an address when its bar is picked', async ({ page, dashboard }) => {
    const bars = dashboard.sourcesCard.getByTestId('bar-slot')

    await bars.first().hover()
    await expect(dashboard.sourcesCard.getByTestId('chart-tooltip-hint')).toHaveText(
      'Click to open',
    )
    await bars.first().click()

    await expect(page).toHaveURL(/\/logs\?q=/)
    expect(decodeURIComponent(new URL(page.url()).searchParams.get('q') ?? '')).toBe(
      'kind:firewall severity>=low from:203.0.113.9 since:24h',
    )
  })

  test('opens the alerts of an hour in the logs, and the keyboard does the same with Enter', async ({
    page,
    dashboard,
  }) => {
    const chart = dashboard.alertsCard.getByRole('img')

    await chart.focus()
    await page.keyboard.press('End')
    await page.keyboard.press('Enter')

    await expect(page).toHaveURL(/\/logs\?q=/)
    const search = decodeURIComponent(new URL(page.url()).searchParams.get('q') ?? '')
    expect(search).toMatch(/^kind:alert since:\S+Z before:\S+Z$/)
  })

  for (const scheme of ['light', 'dark'] as const) {
    test(`textures each series when patterns are on, in the ${scheme} theme`, async ({
      page,
      dashboard,
    }) => {
      await page.emulateMedia({ colorScheme: scheme })
      const bar = dashboard.alertsCard.getByTestId('bar').first()
      await expect(bar).not.toHaveCSS('fill', /url\(/)

      await dashboard.alertsCard.getByTestId('chart-patterns-toggle').click()

      await expect(page.locator('html')).toHaveAttribute('data-patterns', 'on')
      await expect(bar).toHaveCSS('fill', /url\(.*chart-pattern-\d/)
      await expect(dashboard.alertsCard.getByTestId('chart-texture').first()).toBeVisible()
      await expectAccessible(page)

      // It is remembered in this browser.
      await page.reload()
      await expect(page.locator('html')).toHaveAttribute('data-patterns', 'on')
      await expect(dashboard.alertsCard.getByTestId('chart-patterns-toggle')).toHaveAttribute(
        'aria-pressed',
        'true',
      )
    })
  }

  test('textures them in forced-colors mode without being asked, and dashes the lines', async ({
    page,
    dashboard,
  }) => {
    await page.emulateMedia({ forcedColors: 'active' })

    await expect(dashboard.alertsCard.getByTestId('bar').first()).toHaveCSS('fill', /url\(/)
    const lines = dashboard.trafficChart.getByTestId('line')
    await expect(lines.nth(1)).not.toHaveCSS('stroke-dasharray', 'none')
  })

  test('shows the same texture in the table of numbers', async ({ dashboard }) => {
    await dashboard.alertsCard.getByTestId('chart-patterns-toggle').click()

    await dashboard.alertsCard.getByTestId('chart-view').click()

    await expect(dashboard.alertsCard.getByTestId('chart-table-texture').first()).toBeVisible()
  })
})
