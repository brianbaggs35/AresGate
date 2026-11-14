import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const WAITING = '93.184.216.34'
const BANNED = '8.8.4.10'
const BLOCKED = '8.8.4.11'
const ENDED = '8.8.4.12'
const QUIET = '8.8.4.13'
const OLD = '8.8.4.14'

/** What the programs did about six incidents: one nothing has answered, one CrowdSec banned, one
 * the firewall turned away, one whose ban ran out, a sweep too minor to count, and one that went
 * quiet ten days ago. */
const INCIDENTS: IncidentRequest[] = [
  { address: WAITING, severity: 'critical', programs: ['wazuh'], signals: 2, minutes_ago: 5 },
  { address: BANNED, severity: 'high', signals: 2, ban: true, minutes_ago: 20 },
  { address: BLOCKED, severity: 'medium', signals: 2, blocks: 4, dropped: 1, minutes_ago: 30 },
  { address: ENDED, severity: 'high', ban: true, ban_left: '5m', minutes_ago: 300 },
  { address: QUIET, severity: 'low', scan: true, minutes_ago: 15 },
  { address: OLD, severity: 'high', idle_days: 10 },
]

test.describe('incident response', () => {
  test('is in the menu directly under Incidents, and says what the page is for', async ({
    shell,
    incidentResponse,
    page,
  }) => {
    await page.goto('/incidents')

    await shell.goTo('incident-response')

    await expect(page).toHaveURL('/incident-response')
    await shell.expectCurrent('incident-response')
    await expect(incidentResponse.heading).toHaveText('Incident response')
    await expect(shell.pageTitle).toHaveText('Incident response')
  })

  test('says that nothing is going on when nothing serious is', async ({ incidentResponse }) => {
    await incidentResponse.goto()

    await expect(incidentResponse.heroTitle).toHaveText('No serious incidents in the last 7 days')
    await expect(incidentResponse.hero).toHaveAttribute('data-tone', 'idle')
    await expect(incidentResponse.rows).toHaveCount(0)
    await expect(incidentResponse.scope).toContainText('medium severity or higher')
  })

  test('leads with what still needs a response, then puts each incident where it belongs', async ({
    harness,
    incidentResponse,
  }) => {
    await harness.createIncidents(INCIDENTS)

    await incidentResponse.goto()

    await expect(incidentResponse.heroTitle).toHaveText('1 incident still needs a response')
    await expect(incidentResponse.hero).toHaveAttribute('data-tone', 'urgent')
    await expect(incidentResponse.rowsIn('needs_response')).toHaveCount(1)
    await expect(incidentResponse.rowsIn('needs_response')).toContainText(WAITING)
    await expect(incidentResponse.rowsIn('needs_response')).toContainText(
      'Nothing has banned it or turned it away.',
    )
    await expect(incidentResponse.rowsIn('banned')).toHaveCount(1)
    await expect(incidentResponse.rowsIn('banned')).toContainText(BANNED)
    await expect(incidentResponse.rowsIn('banned')).toContainText(
      /CrowdSec banned it, with 3h \d+m left\./,
    )
    await expect(incidentResponse.rowsIn('blocked')).toHaveCount(1)
    await expect(incidentResponse.rowsIn('blocked')).toContainText(
      'The firewall turned it away 4 times and Suricata stopped 1 alert.',
    )
    await expect(incidentResponse.rowsIn('ban_ended')).toHaveCount(1)
    await expect(incidentResponse.rowsIn('ban_ended')).toContainText(ENDED)
    // The groups come in order, those that wait first, and each says how many are in it.
    await expect(incidentResponse.counts).toHaveText([
      'Needs a response: 1',
      'Banned: 1',
      'Turned away: 1',
      'Ban ended: 1',
    ])
    // A sweep too minor to count, and what went quiet more than a week ago, are not listed.
    await expect(incidentResponse.rows).toHaveCount(4)
    await expect(incidentResponse.row(QUIET)).toHaveCount(0)
    await expect(incidentResponse.row(OLD)).toHaveCount(0)
  })

  test('opens the incident from its row', async ({ harness, incidentResponse, page }) => {
    await harness.createIncidents(INCIDENTS)
    await incidentResponse.goto()

    await incidentResponse.row(WAITING).getByTestId('response-link').click()

    await expect(page).toHaveURL(/\/incidents\/\d+$/)
  })

  test('says so once nothing is waiting any more', async ({ harness, incidentResponse }) => {
    await harness.createIncidents([
      INCIDENTS[1] as IncidentRequest,
      INCIDENTS[2] as IncidentRequest,
    ])

    await incidentResponse.goto()

    await expect(incidentResponse.heroTitle).toHaveText('Everything that matters has been answered')
    await expect(incidentResponse.hero).toHaveAttribute('data-tone', 'calm')
    await expect(incidentResponse.noneWaiting).toHaveText('Nothing is waiting for a response.')
  })

  test('looks further back when asked, and again from the top when the range changes', async ({
    harness,
    incidentResponse,
  }) => {
    await harness.createIncidents(INCIDENTS)
    await incidentResponse.goto()
    await expect(incidentResponse.row(OLD)).toHaveCount(0)

    await incidentResponse.range('30d').click()

    await expect(incidentResponse.row(OLD)).toHaveCount(1)
    await expect(incidentResponse.scope).toContainText('the last 30 days')

    await incidentResponse.range('24h').click()

    await expect(incidentResponse.row(OLD)).toHaveCount(0)
    await expect(incidentResponse.rows).toHaveCount(4)
  })

  test('says what it cannot see while CrowdSec and OPNsense are not connected', async ({
    harness,
    incidentResponse,
    page,
  }) => {
    await harness.createIncidents(INCIDENTS)

    await incidentResponse.goto()

    await expect(incidentResponse.coverage).toContainText(
      "CrowdSec and OPNsense aren't connected, so AresGate can't see any ban or block.",
    )
    await incidentResponse.connect.click()
    await expect(page).toHaveURL('/integrations')
  })
})
