import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const ATTACKER = '93.184.216.34'

/** Three attacks heard from at different times, each on a device of its own, the first called nas. */
const SOME: IncidentRequest[] = [
  {
    address: ATTACKER,
    severity: 'critical',
    programs: ['wazuh', 'opnsense'],
    signals: 4,
    minutes_ago: 4,
    device: '192.168.1.20',
    device_name: 'nas',
  },
  {
    address: '8.8.8.8',
    severity: 'high',
    programs: ['wazuh'],
    signals: 2,
    minutes_ago: 35,
    device: '192.168.1.21',
  },
  {
    address: '1.1.1.1',
    severity: 'medium',
    programs: ['ntopng'],
    signals: 1,
    minutes_ago: 180,
    device: '192.168.1.22',
  },
]

test.describe('narrowing by time and device', () => {
  test('on the incidents, with choices that write the search', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(3)
    const scope = page.getByTestId('scope')

    await scope.getByTestId('scope-when').click()
    await page.getByRole('option', { name: 'The last hour' }).click()

    await expect(page).toHaveURL(/q=since:1h/)
    await expect(incidents.searchBox).toHaveValue('since:1h')
    await expect(incidents.cards).toHaveCount(2)

    await scope.getByRole('textbox', { name: 'Device' }).fill('nas')
    await scope.getByRole('textbox', { name: 'Device' }).press('Enter')

    await expect(incidents.searchBox).toHaveValue('since:1h device:nas')
    await expect(incidents.cards).toHaveCount(1)
    await expect(incidents.cards.first()).toContainText(ATTACKER)

    await scope.getByRole('textbox', { name: 'Device' }).clear()
    await scope.getByRole('textbox', { name: 'Device' }).press('Enter')

    await expect(incidents.searchBox).toHaveValue('since:1h')
    await expect(incidents.cards).toHaveCount(2)
  })

  test('on the logs, and a search typed by hand shows in the choices', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents([
      {
        source: 'opnsense',
        kind: 'firewall',
        severity: 'info',
        summary: 'Blocked tcp from 203.0.113.7',
        src_address: '203.0.113.7',
        seconds_ago: 60,
      },
      {
        source: 'wazuh',
        kind: 'alert',
        severity: 'high',
        summary: 'sshd: Failed password for root',
        src_address: '203.0.113.7',
        seconds_ago: 7200,
      },
    ])
    await logs.goto()
    await expect(logs.events).toHaveCount(2)
    const scope = page.getByTestId('scope')

    await scope.getByTestId('scope-when').click()
    await page.getByRole('option', { name: 'The last hour' }).click()

    await expect(logs.events).toHaveCount(1)
    await expect(logs.events.first()).toContainText('Blocked tcp')

    await logs.searchBox.fill('since:30d')
    await logs.searchBox.press('Enter')

    await expect(logs.events).toHaveCount(2)
    await expect(scope.getByRole('combobox', { name: 'When' })).toHaveValue('The last 30 days')
  })
})
