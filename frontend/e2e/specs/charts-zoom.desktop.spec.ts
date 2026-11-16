import { expect, test } from '../support'

const BUSY = {
  collectors: ['ok' as const],
  alerts: { critical: 1, high: 1, medium: 2, low: 1 },
  blocked: { '203.0.113.9': 5, '198.51.100.7': 2 },
  traffic: { igc0: 80, igc1: 5 },
  devices: 2,
}

// The traffic chart is dragged, clicked and zoomed with a mouse, which a phone does not have.
test.describe('the traffic chart you can act on', () => {
  test.beforeEach(async ({ harness, dashboard }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()
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
})
