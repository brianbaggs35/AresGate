import type { Locator, Page } from '@playwright/test'

import { expect, test, waitForMotion } from '../support'

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

  // The firewall's counters are of the last three hours, the right end of a day's plot.
  const DATA = 0.95
  const EARLIER = [0.3, 0.6] as const

  /** Where a part of the plot is, measured once the chart is in view and has stopped moving. */
  async function plotAt(page: Page, chart: Locator) {
    const svg = chart.getByRole('img')
    await svg.scrollIntoViewIfNeeded()
    await waitForMotion(page)
    const box = await svg.boundingBox()
    if (!box) throw new Error('The chart is not on the page.')
    return {
      x: (share: number) => box.x + box.width * share,
      y: box.y + box.height / 2,
    }
  }

  test('opens the logs of a moment of the traffic when it is clicked', async ({
    page,
    dashboard,
  }) => {
    const plot = await plotAt(page, dashboard.trafficChart)

    await page.mouse.click(plot.x(DATA), plot.y)

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
    // The hours are drawn once the alerts have loaded, so what there is to narrow is counted then.
    await expect(hours).not.toHaveCount(0)
    const before = await hours.count()
    await expect(dashboard.trafficChart.getByTestId('chart-zoom-reset')).toBeHidden()
    const plot = await plotAt(page, dashboard.trafficChart)

    // Several hours wide, so the span holds more than one start of an hour whenever it is run.
    await page.mouse.move(plot.x(0.75), plot.y)
    await page.mouse.down()
    await page.mouse.move(plot.x(0.98), plot.y, { steps: 8 })
    await expect(dashboard.trafficChart.getByTestId('chart-selection')).toBeVisible()
    await page.mouse.up()

    await expect(dashboard.trafficChart.getByTestId('chart-zoom-reset')).toBeVisible()
    await expect(dashboard.trafficChart.getByTestId('line')).toHaveCount(2)
    await expect(hours).not.toHaveCount(before)

    await dashboard.trafficChart.getByTestId('chart-zoom-reset').click()

    await expect(dashboard.trafficChart.getByTestId('chart-zoom-reset')).toBeHidden()
    await expect(hours).toHaveCount(before)
  })

  test('can be put back after zooming into a stretch with no traffic in it', async ({
    page,
    dashboard,
  }) => {
    const plot = await plotAt(page, dashboard.trafficChart)

    await page.mouse.move(plot.x(EARLIER[0]), plot.y)
    await page.mouse.down()
    await page.mouse.move(plot.x(EARLIER[1]), plot.y, { steps: 8 })
    await page.mouse.up()

    await expect(dashboard.trafficChart.getByTestId('chart-empty')).toContainText(
      'Nothing in this stretch',
    )
    await dashboard.trafficChart.getByTestId('chart-zoom-reset').click()

    await expect(dashboard.trafficChart.getByTestId('chart-empty')).toBeHidden()
    await expect(dashboard.trafficChart.getByTestId('line')).toHaveCount(2)
  })

  test('zooms with Shift and the arrow keys, then Enter', async ({ page, dashboard }) => {
    const chart = dashboard.trafficChart.getByRole('img')

    await chart.focus()
    await page.keyboard.press('End')
    await page.keyboard.down('Shift')
    // A short stretch of the latest readings, which has some traffic in it.
    for (let step = 0; step < 2; step++) await page.keyboard.press('ArrowLeft')
    await page.keyboard.up('Shift')
    await page.keyboard.press('Enter')

    await expect(dashboard.trafficChart.getByTestId('chart-zoom-reset')).toBeVisible()
    await expect(dashboard.trafficChart.getByTestId('line')).toHaveCount(2)
  })
})
