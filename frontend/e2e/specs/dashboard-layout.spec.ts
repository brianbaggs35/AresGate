import type { Locator } from '@playwright/test'

import { expect, test } from '../support'

/** What the dashboard is shown in these: serious alerts, refused connections and one interface. */
const BUSY = {
  collectors: ['ok' as const],
  alerts: { critical: 1, high: 1, medium: 2, low: 1 },
  blocked: { '203.0.113.9': 5, '198.51.100.7': 2 },
  traffic: { igc0: 80 },
}

/** The names the dashboard's widgets are drawn under, in the order they are on the page. */
const order = (widgets: Locator) =>
  widgets.evaluateAll((items) => items.map((item) => item.getAttribute('data-test')))

test.describe('dashboard layout', () => {
  test('starts as the overview, with every widget the dashboard has data for', async ({
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)

    await dashboard.goto()

    await expect(dashboard.trafficCard).toBeVisible()
    await expect(dashboard.alertsCard).toBeVisible()
    await expect(dashboard.sourcesCard).toBeVisible()
    await expect(dashboard.latestAlerts).toBeVisible()
  })

  test('hides a widget from the sheet, and still has it hidden after a reload', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()
    await dashboard.customize.click()
    await expect(dashboard.sheet).toBeVisible()

    await dashboard.sheetRow('sources').getByRole('checkbox').uncheck()
    await expect(dashboard.sourcesCard).toBeHidden()

    await page.reload()
    await expect(dashboard.alertsCard).toBeVisible()
    await expect(dashboard.sourcesCard).toBeHidden()
  })

  test('moves a widget with its arrows, and keeps the order after a reload', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()
    await expect(dashboard.alertsCard).toBeVisible()
    const before = await order(dashboard.widgets)
    await dashboard.customize.click()

    await dashboard.sheetRow('filtered').getByTestId('widget-down').click()

    await expect(dashboard.sheetStatus).toHaveText('What was left out is now number 2 of 9.')
    await page.reload()
    await expect(dashboard.alertsCard).toBeVisible()
    const after = await order(dashboard.widgets)
    expect(after.slice(0, 2)).toEqual([before[1], before[0]])
  })

  test('makes a widget the full width of the page', async ({ page, harness, dashboard }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()
    await dashboard.customize.click()

    await dashboard.sheetRow('alerts').getByTestId('widget-full').click()
    await dashboard.sheetDone.click()

    await expect(dashboard.sheet).toBeHidden()
    const box = await dashboard.alertsCard.boundingBox()
    const row = await page.getByTestId('widgets').boundingBox()
    expect(box!.width).toBeGreaterThan(row!.width * 0.9)
  })

  test('starts over from a preset, and goes back to the default', async ({
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()
    await dashboard.customize.click()

    await dashboard.preset('compact').click()
    await expect(dashboard.preset('compact')).toHaveAttribute('aria-pressed', 'true')
    await expect(dashboard.sourcesCard).toBeVisible()
    await expect(dashboard.sheetRow('blocked').getByRole('checkbox')).not.toBeChecked()

    await dashboard.sheetReset.click()
    await expect(dashboard.preset('overview')).toHaveAttribute('aria-pressed', 'true')
    await expect(dashboard.sheetRow('blocked').getByRole('checkbox')).toBeChecked()
  })

  test('says what a widget needs when nothing that feeds it is connected', async ({
    page,
    dashboard,
  }) => {
    await dashboard.goto()

    await expect(page.getByTestId('widget-needs-words').first()).toContainText('Connect')
    await expect(page.getByTestId('widget-needs-link').first()).toHaveAttribute(
      'href',
      '/integrations',
    )
  })
})

test.describe('wall display', () => {
  test('is the dashboard alone, and the page leaves it by its button', async ({
    page,
    shell,
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()

    await dashboard.wall.click()

    await expect(page).toHaveURL('/?wall=1')
    await expect(dashboard.wallExit).toBeVisible()
    await expect(dashboard.range).toBeHidden()
    await expect(shell.menu).toBeHidden()
    await expect(dashboard.banner).toBeVisible()

    await dashboard.wallExit.click()

    await expect(page).toHaveURL('/')
    await expect(shell.menu).toBeVisible()
  })

  test('is opened by its address, and shows an alarm while something needs the owner', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await harness.createIncidents([
      {
        address: '93.184.216.34',
        severity: 'critical',
        programs: ['wazuh', 'opnsense'],
        signals: 4,
        ban: true,
        minutes_ago: 30,
      },
    ])

    await page.goto('/?wall')

    await expect(dashboard.wallAlarm).toContainText(/needs? you now/)
    await expect(dashboard.wallFullscreen).toBeVisible()
  })

  test('shows no alarm when nothing needs the owner', async ({ page, harness, dashboard }) => {
    await harness.createActivity({ collectors: ['ok'] })

    await page.goto('/?wall')

    await expect(dashboard.banner).toBeVisible()
    await expect(dashboard.wallAlarm).toBeHidden()
  })
})
