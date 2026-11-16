import { expect, expectAccessible, test } from '../support'

const BUSY = {
  collectors: ['ok' as const],
  alerts: { critical: 1, high: 1, medium: 2, low: 1 },
  blocked: { '203.0.113.9': 5, '198.51.100.7': 2 },
  traffic: { igc0: 80, igc1: 5 },
  devices: 2,
}

test.describe('the numbers on the dashboard open what they count', () => {
  test.beforeEach(async ({ harness, dashboard }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()
  })

  test('the alerts tile opens as many alerts as it says', async ({ page, dashboard, logs }) => {
    await expect(dashboard.alertsTile).toHaveAccessibleName(
      '5 alerts in the last 24 hours, show them',
    )
    await expect(dashboard.alertsTile.getByTestId('stat-go')).toBeVisible()

    await dashboard.alertsTile.click()

    await expect(page).toHaveURL(/\/logs\?q=/)
    await expect(logs.matched).toHaveText('5 events')
  })

  test('the blocked tile opens as many blocks as it says', async ({ page, dashboard, logs }) => {
    await expect(dashboard.blockedTile).toHaveAccessibleName(
      '7 blocked connections in the last 24 hours, show them',
    )

    await dashboard.blockedTile.click()

    await expect(page).toHaveURL(/\/logs\?q=/)
    await expect(logs.matched).toHaveText('7 events')
  })

  test('a tile is reached and opened with the keyboard, and shows where the focus is', async ({
    page,
    dashboard,
  }) => {
    await dashboard.alertsTile.focus()
    await expect(dashboard.alertsTile).toBeFocused()
    await expect(dashboard.alertsTile).toHaveCSS('outline-style', 'solid')

    await page.keyboard.press('Enter')

    await expect(page).toHaveURL(/\/logs\?q=/)
  })
})

for (const theme of ['light', 'dark'] as const) {
  test.describe(`what is new since the last look, in the ${theme} theme`, () => {
    test('is told once, opens what it counted, and goes when dismissed', async ({
      page,
      harness,
      dashboard,
      incidents,
      shell,
    }) => {
      // The first visit has nothing to compare with, so it says nothing.
      const first = page.waitForResponse(/\/api\/dashboard\/since$/)
      await dashboard.goto()
      await first
      await expect(page.getByTestId('since')).toBeHidden()

      await harness.createIncidents([
        { severity: 'high', minutes_ago: 0, signals: 1 },
        { severity: 'low', minutes_ago: 0, signals: 1 },
      ])
      await page.reload()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      const banner = page.getByTestId('since')
      await expect(banner).toBeVisible()
      await expect(banner).toContainText('Since you last looked')
      await expect(banner.getByTestId('since-incidents')).toHaveText(
        '2 new incidents (1 high, 1 low)',
      )
      await expectAccessible(page)

      await banner.getByTestId('since-incidents').click()
      await expect(page).toHaveURL(/\/incidents\?/)
      await expect(incidents.cards).toHaveCount(2)

      // Having been told, it is not told again.
      await dashboard.goto()
      await expect(banner).toBeHidden()
    })

    test('goes when dismissed, and stays gone', async ({ page, harness, dashboard, shell }) => {
      const first = page.waitForResponse(/\/api\/dashboard\/since$/)
      await dashboard.goto()
      await first
      await harness.createIncidents([{ severity: 'critical', minutes_ago: 0, signals: 1 }])
      await page.reload()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      const banner = page.getByTestId('since')
      await expect(banner.getByTestId('since-incidents')).toHaveText('1 new incident (1 critical)')
      await banner.getByRole('button', { name: 'Dismiss what is new' }).click()
      await expect(banner).toBeHidden()

      await page.reload()
      await expect(dashboard.alertsTile).toBeVisible()
      await expect(banner).toBeHidden()
    })
  })
}
