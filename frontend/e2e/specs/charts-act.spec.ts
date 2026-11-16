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

  test('opens the logs of a moment of the traffic when it is clicked', async ({
    page,
    dashboard,
  }) => {
    const plot = await dashboard.trafficChart.getByRole('img').boundingBox()
    await dashboard.trafficChart.getByRole('img').scrollIntoViewIfNeeded()

    await page.mouse.click((plot?.x ?? 0) + (plot?.width ?? 0) * 0.5, (plot?.y ?? 0) + 80)

    await expect(page).toHaveURL(/\/logs\?q=/)
    expect(decodeURIComponent(new URL(page.url()).searchParams.get('q') ?? '')).toMatch(
      /^kind:firewall since:\S+Z before:\S+Z$/,
    )
  })

  test('zooms the page to a span dragged across the traffic, and resets it', async ({
    page,
    dashboard,
  }) => {
    const hours = dashboard.alertsCard.getByTestId('bar-slot')
    const before = await hours.count()
    await expect(dashboard.trafficChart.getByTestId('chart-zoom-reset')).toBeHidden()
    await dashboard.trafficChart.getByRole('img').scrollIntoViewIfNeeded()
    const plot = await dashboard.trafficChart.getByRole('img').boundingBox()
    const y = (plot?.y ?? 0) + 80

    await page.mouse.move((plot?.x ?? 0) + (plot?.width ?? 0) * 0.3, y)
    await page.mouse.down()
    await page.mouse.move((plot?.x ?? 0) + (plot?.width ?? 0) * 0.6, y, { steps: 8 })
    await expect(dashboard.trafficChart.getByTestId('chart-selection')).toBeVisible()
    await page.mouse.up()

    await expect(dashboard.trafficChart.getByTestId('chart-zoom-reset')).toBeVisible()
    await expect(hours).not.toHaveCount(before)

    await dashboard.trafficChart.getByTestId('chart-zoom-reset').click()

    await expect(dashboard.trafficChart.getByTestId('chart-zoom-reset')).toBeHidden()
    await expect(hours).toHaveCount(before)
  })

  test('zooms with Shift and the arrow keys, then Enter', async ({ page, dashboard }) => {
    const chart = dashboard.trafficChart.getByRole('img')

    await chart.focus()
    await page.keyboard.press('Home')
    await page.keyboard.down('Shift')
    // A short stretch, which is part of the chart however few moments a narrow one draws.
    for (let step = 0; step < 2; step++) await page.keyboard.press('ArrowRight')
    await page.keyboard.up('Shift')
    await page.keyboard.press('Enter')

    await expect(dashboard.trafficChart.getByTestId('chart-zoom-reset')).toBeVisible()
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
