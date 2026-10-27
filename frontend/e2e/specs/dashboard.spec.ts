import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

/** What the dashboard is shown in most of these: two serious alerts among five, seven refused
 * connections, two interfaces and two new devices. */
const BUSY = {
  collectors: ['ok' as const],
  alerts: { critical: 1, high: 1, medium: 2, low: 1 },
  blocked: { '203.0.113.9': 5, '198.51.100.7': 2 },
  traffic: { igc0: 80, igc1: 5 },
  devices: 2,
}

const ATTACKER = '93.184.216.34'

/** Two open incidents: a quiet scan that was heard from a moment ago, and a serious attack that
 * two programs saw and CrowdSec banned, half an hour ago. */
const WAITING: IncidentRequest[] = [
  { address: '8.8.8.8', severity: 'low', programs: ['opnsense'], signals: 1, minutes_ago: 3 },
  {
    address: ATTACKER,
    severity: 'critical',
    programs: ['wazuh', 'opnsense'],
    signals: 4,
    ban: true,
    minutes_ago: 30,
  },
]

test.describe('dashboard', () => {
  test('is the first page, and asks for something to be connected on a new install', async ({
    page,
    dashboard,
  }) => {
    await dashboard.goto()

    await expect(page).toHaveTitle('Dashboard · AresGate')
    await expect(dashboard.heading).toHaveText('Dashboard')
    await expect(dashboard.banner).toHaveAttribute('data-state', 'setup')
    await expect(dashboard.bannerTitle).toHaveText('Nothing is watching yet')
    await expect(dashboard.collectionTile).toContainText('None')
    await expect(dashboard.alertsTile).toContainText('Alerts')
    await expect(dashboard.alertsTile).toContainText('None, as in the day before')
    await expect(dashboard.trafficChart.getByTestId('chart-empty')).toContainText(
      'No traffic recorded yet',
    )
    await expect(dashboard.alertsCard.getByTestId('chart-empty')).toContainText('No alerts')
    await expect(dashboard.sourcesCard.getByTestId('chart-empty')).toContainText(
      'Nothing was blocked',
    )
    await expect(dashboard.latestAlerts).toContainText('No alerts')
    await expect(dashboard.updated).toContainText('Updated')
  })

  test('leads from the banner to where an integration is connected', async ({
    page,
    dashboard,
  }) => {
    await dashboard.goto()

    await dashboard.bannerAction.click()

    await expect(page).toHaveURL('/integrations')
  })

  test('says all is quiet once a firewall is connected and nothing has happened', async ({
    harness,
    dashboard,
  }) => {
    await harness.createActivity({ collectors: ['ok'] })

    await dashboard.goto()

    await expect(dashboard.banner).toHaveAttribute('data-state', 'calm')
    await expect(dashboard.bannerTitle).toHaveText('All quiet')
    await expect(dashboard.bannerDetail).toHaveText('No alerts in the last 24 hours.')
    await expect(dashboard.bannerAction).toBeHidden()
    await expect(dashboard.collectionTile).toContainText('Working')
    await expect(dashboard.collectionTile).toContainText('1 collector')
    await expect(dashboard.needsYou).toBeHidden()
  })

  test('puts the incidents that need a decision under the banner, the most serious first', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await harness.createIncidents(WAITING)

    await dashboard.goto()

    await expect(dashboard.needsYou.getByRole('heading', { name: 'Needs you' })).toBeVisible()
    await expect(dashboard.needsYouCards.getByTestId('incident-title')).toHaveText([
      `Brute force on ssh (${ATTACKER})`,
      'Brute force on ssh (8.8.8.8)',
    ])
    await expect(dashboard.needsYouAll).toHaveText('Open Incidents')

    await dashboard.needsYouAll.click()

    await expect(page).toHaveURL('/incidents')
  })

  test('says what was remembered when a verdict is given from the lane, and takes it back', async ({
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await harness.createIncidents(WAITING)
    await dashboard.goto()

    await dashboard.quick('not_suspicious').click()

    await expect(dashboard.judged).toHaveText(`Remembered: ${ATTACKER} is not suspicious.`)
    await expect(dashboard.needsYouCards).toHaveCount(1)
    await expect(dashboard.needsYouCards.getByTestId('incident-title')).toHaveText(
      'Brute force on ssh (8.8.8.8)',
    )

    await dashboard.undo.click()

    await expect(dashboard.judged).toHaveText('Taken back.')
    await expect(dashboard.needsYouCards).toHaveCount(2)
  })

  test('says the collectors are starting until one has run', async ({ harness, dashboard }) => {
    await harness.createActivity({ collectors: ['waiting'] })

    await dashboard.goto()

    await expect(dashboard.banner).toHaveAttribute('data-state', 'calm')
    await expect(dashboard.collectionTile).toContainText('Starting')
  })

  test('never says all is quiet while a collector is failing', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity({ collectors: ['ok', 'problem'] })

    await dashboard.goto()

    await expect(dashboard.banner).toHaveAttribute('data-state', 'watch')
    await expect(dashboard.bannerTitle).toHaveText("Some sources aren't reporting")
    await expect(dashboard.bannerDetail).toHaveText(
      'No alerts in the last 24 hours. 1 collector is not working, so a quiet network may not be a safe one.',
    )
    await expect(dashboard.collectionTile).toContainText('1 failing')
    await expect(dashboard.collectionTile).toContainText('2 collectors')

    await dashboard.bannerAction.click()

    await expect(page).toHaveURL('/status')
  })

  test('leads from the collection tile to the status page', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity({ collectors: ['ok'] })
    await dashboard.goto()

    await dashboard.collectionTile.click()

    await expect(page).toHaveURL('/status')
  })

  test('asks for attention when there are serious alerts, and counts what happened', async ({
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)

    await dashboard.goto()

    await expect(dashboard.banner).toHaveAttribute('data-state', 'attention')
    await expect(dashboard.bannerTitle).toHaveText('Needs your attention')
    await expect(dashboard.bannerDetail).toHaveText(
      '2 serious alerts in the last 24 hours (high or critical).',
    )
    await expect(dashboard.alertsTile.getByTestId('stat-value')).toHaveText('5')
    await expect(dashboard.alertsTile).toContainText('Up from none the day before')
    await expect(dashboard.blockedTile.getByTestId('stat-value')).toHaveText('7')
    await expect(dashboard.devicesTile.getByTestId('stat-value')).toHaveText('2')
    await expect(dashboard.devicesTile).toContainText('2 known, first seen in the last 24 hours')
  })

  test('lists the latest alerts, the newest first, with who reported each', async ({
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)

    await dashboard.goto()

    await expect(dashboard.alertRows.getByTestId('alert-summary')).toHaveText([
      'Critical alert 1',
      'High alert 2',
      'Medium alert 3',
      'Medium alert 4',
      'Low alert 5',
    ])
    await expect(dashboard.alertRows.getByTestId('severity')).toHaveText([
      'Critical',
      'High',
      'Medium',
      'Medium',
      'Low',
    ])
    const first = dashboard.alertRows.first().getByTestId('alert-detail')
    await expect(first).toContainText('OPNsense')
    await expect(first).toContainText('198.51.100.20 → 192.168.1.20')
  })

  test('stacks the alerts by severity and ranks the addresses blocked most', async ({
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)

    await dashboard.goto()

    await expect(dashboard.alertsCard.getByTestId('chart-title')).toHaveText('Alerts by severity')
    await expect(dashboard.alertsCard.getByTestId('chart-legend-label')).toHaveText([
      'Low',
      'Medium',
      'High',
      'Critical',
    ])
    await expect(dashboard.sourcesCard.getByTestId('bar-category')).toHaveText([
      '203.0.113.9',
      '198.51.100.7',
    ])
    await expect(dashboard.sourcesCard.getByTestId('bar-value')).toHaveText(['5', '2'])
  })

  test('charts the traffic of the busiest interface, in bits a second, and reads it', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)

    await dashboard.goto()

    const chart = dashboard.trafficChart
    await expect(chart.getByTestId('chart-title')).toHaveText('Network traffic')
    await expect(chart.getByTestId('chart-caption')).toHaveText(
      "Speed through igc0, from the firewall's byte counters.",
    )
    await expect(chart.getByTestId('line')).toHaveCount(2)
    await expect(chart.getByTestId('chart-legend-label')).toHaveText(['Received', 'Sent'])

    // Pointing near the end of the data, an hour or more before the end of the day.
    await chart.getByRole('img').scrollIntoViewIfNeeded()
    const plot = await chart.getByRole('img').boundingBox()
    await page.mouse.move((plot?.x ?? 0) + (plot?.width ?? 0) * 0.9, (plot?.y ?? 0) + 80)
    await expect(chart.getByTestId('chart-tooltip')).toContainText('80 Mb/s')
    await expect(chart.getByTestId('chart-tooltip')).toContainText('20 Mb/s')
    await expect(chart.getByRole('status')).toContainText('80 Mb/s Received')
    await page.mouse.move(0, 0)
    await expect(chart.getByTestId('chart-tooltip')).toBeHidden()

    await chart.getByTestId('chart-view').click()
    await expect(chart.getByRole('columnheader')).toHaveText(['Time', 'Received', 'Sent'])
    await expect(
      chart.getByTestId('chart-table-row').filter({ hasText: '80 Mb/s' }).first(),
    ).toContainText('20 Mb/s')
  })

  test('flags the incidents that began in the day on the traffic, and links to each', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await harness.createIncidents(WAITING)

    await dashboard.goto()

    // The serious one is flagged; the quiet scan is not worth a flag.
    await expect(dashboard.trafficFlags).toHaveCount(1)
    const flag = dashboard.trafficFlags.first()
    await expect(flag).toHaveAccessibleName(`Critical incident: Brute force on ssh (${ATTACKER})`)
    await expect(dashboard.trafficFlagCounts).toHaveCount(0)

    await flag.hover()
    await expect(dashboard.trafficChart.getByTestId('chart-tooltip')).toContainText(/Began/)
    await expect(dashboard.trafficChart.getByTestId('chart-tooltip')).toContainText(
      `Brute force on ssh (${ATTACKER})`,
    )
    await expect(dashboard.trafficChart.getByTestId('chart-tooltip')).toContainText('Banned')
    await expect(dashboard.trafficChart.getByTestId('chart-tooltip')).toContainText(
      'by an integration',
    )

    await dashboard.trafficChart.getByTestId('chart-view').click()
    await expect(dashboard.trafficChart.getByRole('columnheader')).toHaveText([
      'Time',
      'Received',
      'Sent',
      'Incidents',
    ])
    await expect(
      dashboard.trafficChart
        .getByTestId('chart-table-row')
        .filter({ hasText: `Critical incident: Brute force on ssh (${ATTACKER})` }),
    ).toHaveCount(1)

    await dashboard.trafficChart.getByTestId('chart-view').click()
    await flag.click()
    await expect(page).toHaveURL(/\/incidents\/\d+$/)
  })

  test('leaves the traffic without flags when nothing serious began', async ({
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await harness.createIncidents([WAITING[0] as IncidentRequest])

    await dashboard.goto()

    await expect(dashboard.trafficChart.getByTestId('line')).toHaveCount(2)
    await expect(dashboard.trafficFlags).toHaveCount(0)
    await dashboard.trafficChart.getByTestId('chart-view').click()
    await expect(dashboard.trafficChart.getByRole('columnheader')).toHaveText([
      'Time',
      'Received',
      'Sent',
    ])
  })

  test('charts another interface when asked', async ({ page, harness, dashboard }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()
    await expect(dashboard.trafficChart.getByTestId('chart-caption')).toContainText('igc0')

    await dashboard.trafficInterface.click()
    await page.getByRole('option', { name: 'igc1' }).click()

    await expect(dashboard.trafficChart.getByTestId('chart-caption')).toContainText('igc1')
    await dashboard.trafficChart.getByTestId('chart-view').click()
    await expect(
      dashboard.trafficChart.getByTestId('chart-table-row').filter({ hasText: '5 Mb/s' }).first(),
    ).toContainText('1.25 Mb/s')
  })

  test('looks at the last 7 days when asked, and back at the day', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity(BUSY)
    await dashboard.goto()
    await expect(dashboard.alertsTile).toContainText('In the last 24 hours')

    const [week] = await Promise.all([
      page.waitForRequest((request) => request.url().includes('/api/dashboard?window=7d')),
      dashboard.week.click(),
    ])

    expect(week.method()).toBe('GET')
    await expect(dashboard.alertsTile).toContainText('In the last 7 days')
    await expect(dashboard.alertsTile).toContainText('Up from none the week before')
    await expect(dashboard.alertsTile.getByTestId('stat-value')).toHaveText('5')
    await expect(dashboard.bannerDetail).toContainText('in the last 7 days')

    await dashboard.day.click()

    await expect(dashboard.alertsTile).toContainText('In the last 24 hours')
  })

  test('asks again when told to', async ({ page, dashboard }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    const [again] = await Promise.all([
      page.waitForRequest((request) => request.url().includes('/api/dashboard')),
      dashboard.refresh.click(),
    ])

    expect(again.method()).toBe('GET')
    await expect(dashboard.banner).toBeVisible()
  })

  test('asks again by itself every half minute while it is open', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity({ collectors: ['ok'] })
    await page.clock.install()
    await dashboard.goto()
    await expect(dashboard.banner).toHaveAttribute('data-state', 'calm')
    await harness.createActivity({ ...BUSY, collectors: [] })

    await page.clock.runFor(31_000)

    await expect(dashboard.banner).toHaveAttribute('data-state', 'attention')
    await expect(dashboard.alertsTile.getByTestId('stat-value')).toHaveText('5')
  })

  test('says so when it cannot be loaded, and loads when asked to try again', async ({
    page,
    dashboard,
  }) => {
    await page.route('**/api/dashboard*', (route) =>
      route.fulfill({
        status: 500,
        json: { detail: { code: 'broken', message: 'The dashboard is broken.' } },
      }),
    )
    await dashboard.goto()
    await expect(dashboard.error).toBeVisible()
    await expect(dashboard.banner).toBeHidden()

    await page.unroute('**/api/dashboard*')
    await dashboard.retry.click()

    await expect(dashboard.error).toBeHidden()
    await expect(dashboard.banner).toBeVisible()
  })

  test('keeps what it shows when a refresh fails, and says so', async ({ page, dashboard }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    await page.route('**/api/dashboard*', (route) => route.abort())
    await dashboard.refresh.click()

    await expect(dashboard.stale).toContainText("Can't reach AresGate.")
    await expect(dashboard.stale).toContainText('What is shown is from')
    await expect(dashboard.banner).toBeVisible()

    await page.unroute('**/api/dashboard*')
    await dashboard.refresh.click()

    await expect(dashboard.stale).toBeHidden()
  })
})
