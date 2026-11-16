import { connectFirewall } from '../support/flows'
import { expect, expectAccessible, test } from '../support'

const LAPTOP_IP = '192.168.1.20'
const SERVER = '93.184.216.34'
const ADDRESS =
  'https://discord.com/api/webhooks/1234567890123456789/Zk3-_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_x'

for (const theme of ['light', 'dark'] as const) {
  test.describe(`trends beside the lists, in the ${theme} theme`, () => {
    test.beforeEach(async ({ harness }) => {
      await harness.createAssets({
        devices: [
          {
            hostname: 'laptop',
            mac: '00:11:22:0a:0b:0c',
            addresses: [LAPTOP_IP],
            listed: [{ source: 'opnsense', via: 'arp', minutes_ago: 1 }],
          },
        ],
      })
      await harness.createEvents([
        {
          src_address: LAPTOP_IP,
          src_port: 51000,
          dst_address: SERVER,
          dst_port: 443,
          protocol: 'tcp',
          repeat: 6,
          every_seconds: 600,
          seconds_ago: 3600,
        },
      ])
    })

    test('a device in the list shows its week, and its page charts the connections', async ({
      page,
      devices,
      shell,
    }) => {
      await devices.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      const card = devices.cards.filter({ hasText: LAPTOP_IP })
      await expect(card.getByTestId('trend-spark')).toBeVisible()
      await expect(card.getByTestId('trend-spark-label')).toContainText('events in the last 7 days')
      await expectAccessible(page)

      await card.getByTestId('device-link').click()

      const traffic = page.getByTestId('device-traffic')
      await expect(traffic).toBeVisible()
      await expect(
        traffic.getByRole('heading', { name: 'Connections over the week' }),
      ).toBeVisible()
      await expect(traffic.getByTestId('chart-legend-item')).toHaveText([
        /Connections in/,
        /Connections out/,
      ])
      await traffic.getByTestId('chart-view').click()
      await expect(traffic.getByTestId('chart-table')).toBeVisible()
      await expectAccessible(page)
    })

    test('the alerts page charts the messages above the log', async ({ page, alerts, shell }) => {
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      const chart = page.getByTestId('delivery-trend')
      await expect(chart).toBeVisible()
      await expect(chart.getByTestId('chart-title')).toHaveText('Messages by severity')
      await expect(chart.getByTestId('empty-title')).toHaveText('No messages')
      await expectAccessible(page)
    })

    test('the status page shows how each integration went over the last day', async ({
      page,
      harness,
      integration,
      status,
      shell,
    }) => {
      await connectFirewall(harness, integration, ['suricata'])

      await status.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      const strip = status.parts.getByTestId('health-strip').first()
      await expect(strip).toBeVisible()
      await expect(strip.getByTestId('health-summary')).toContainText('In the last 24 hours')
      await expect(strip.getByTestId('health-cell')).toHaveCount(24)
      await expectAccessible(page)
    })
  })
}
