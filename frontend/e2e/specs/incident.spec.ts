import type { Page } from '@playwright/test'

import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const ATTACKER = '93.184.216.34'

/** An attack that three programs saw over twenty minutes, that CrowdSec banned the address of,
 * on a device on the network that is known by name. */
const BAD: IncidentRequest = {
  address: ATTACKER,
  severity: 'critical',
  programs: ['wazuh', 'opnsense', 'crowdsec'],
  signals: 6,
  ban: true,
  minutes_ago: 4,
  device_name: 'nas',
}

/** Opens the page of the incident about an address, from the list, as someone would. */
async function openIncident(page: Page, address: string): Promise<void> {
  await page.goto('/incidents?view=all')
  await page.getByTestId('incident').filter({ hasText: address }).click()
  await expect(page).toHaveURL(/\/incidents\/\d+$/)
}

test.describe('an incident', () => {
  test('says what it is, how serious, what became of it and how sure AresGate is', async ({
    harness,
    incident,
    page,
    shell,
  }) => {
    await harness.createIncidents([BAD])

    await openIncident(page, ATTACKER)

    await expect(page).toHaveTitle('Incidents · AresGate')
    await expect(shell.incidentsLink).toHaveAttribute('aria-current', 'page')
    await expect(incident.heading).toHaveText(`Brute force on ssh (${ATTACKER})`)
    await expect(incident.severity).toHaveText('Critical')
    await expect(incident.status).toHaveText('Open')
    await expect(page.getByTestId('confidence-chip')).toHaveText('High confidence')
    await expect(page.getByTestId('incident-when')).toContainText('First signal')
    await expect(page.getByTestId('incident-meaning')).toContainText(
      "Open: Nobody has said they're looking at it.",
    )
  })

  test('counts its signals, programs, addresses and the firewall’s blocks', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([BAD])

    await openIncident(page, ATTACKER)

    await expect(incident.signalsTile).toContainText('7')
    await expect(incident.programsTile).toContainText('3')
    await expect(incident.programsTile).toContainText('CrowdSec, OPNsense, Wazuh')
    await expect(incident.addressesTile).toContainText('2')
    await expect(incident.addressesTile).toContainText('1 on your network')
    await expect(incident.blockedTile).toContainText('0')
  })

  test('adds up the reasons AresGate is sure, and the points are the confidence', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([BAD])

    await openIncident(page, ATTACKER)

    await expect(incident.reasonsCard).toContainText('Why AresGate is this sure')
    await expect(incident.confidence).toHaveText('High confidence')
    await expect(incident.reasons.getByTestId('reason-label')).toHaveText([
      'Most serious signal',
      'Other programs agree',
      'It keeps happening',
      'Banned',
    ])
    await expect(incident.reasons.getByTestId('reason-points')).toHaveText([
      '+55',
      '+30',
      '+10',
      '+20',
    ])
    await expect(incident.reasonsCard.getByTestId('reasons-total')).toContainText('100')
  })

  test('names the address it is about and the device that was attacked', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([BAD])

    await openIncident(page, ATTACKER)

    await expect(incident.addresses).toHaveCount(2)
    const about = incident.addresses.first()
    await expect(about).toContainText(ATTACKER)
    await expect(about.getByTestId('address-subject')).toHaveText('What it is about')
    await expect(about.getByTestId('address-elsewhere')).toBeVisible()
    const device = incident.addresses.nth(1)
    await expect(device).toContainText('192.168.1.20')
    await expect(device.getByTestId('address-device')).toContainText('nas')
    await expect(device.getByTestId('address-device')).toContainText('E2E Devices')
  })

  test('lists every signal, whichever program saw it, oldest first', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([BAD])

    await openIncident(page, ATTACKER)

    await expect(incident.signals).toHaveCount(7)
    await expect(incident.signals.first()).toContainText('Wazuh')
    await expect(incident.signals.first()).toContainText('Critical')
    await expect(incident.signals.first()).toContainText(
      `${ATTACKER}:40000 → 192.168.1.20:22 (tcp)`,
    )
    await expect(incident.signals.last()).toContainText('CrowdSec')
    await expect(incident.signals.last()).toContainText('Ban')
    await expect(incident.signals.last()).toContainText(`Ban ${ATTACKER} for ssh-bruteforce`)
  })

  test('charts them by program', async ({ harness, incident, page }) => {
    await harness.createIncidents([BAD])

    await openIncident(page, ATTACKER)

    await expect(incident.spreadCard).toContainText('Signals over time')
    await expect(incident.spreadCard.getByTestId('chart-legend-label')).toHaveText([
      'CrowdSec',
      'OPNsense',
      'Wazuh',
    ])
    await incident.spreadCard.getByTestId('chart-view').click()
    await expect(incident.spreadCard.getByRole('table')).toBeVisible()
  })

  test('has no chart for a single signal, which is no story over time', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([{ address: '8.8.8.8', signals: 1 }])

    await openIncident(page, '8.8.8.8')

    await expect(incident.signals).toHaveCount(1)
    await expect(incident.spreadCard).toBeHidden()
    await expect(incident.addressesTile).toContainText('0 on your network')
  })

  test('lists the first of a long timeline, and the rest when asked', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([{ address: ATTACKER, signals: 40, minutes_ago: 1 }])

    await openIncident(page, ATTACKER)

    await expect(incident.signals).toHaveCount(25)
    await page.getByTestId('timeline-show-more').click()
    await expect(incident.signals).toHaveCount(40)
    await expect(page.getByTestId('timeline-show-more')).toBeHidden()
  })

  test('goes back to the list', async ({ harness, incident, page }) => {
    await harness.createIncidents([BAD])
    await openIncident(page, ATTACKER)

    await incident.back.click()

    await expect(page).toHaveURL('/incidents')
  })

  test('is looked into, resolved and reopened, and each change is kept', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([BAD])
    await openIncident(page, ATTACKER)

    await incident.action('investigating').click()

    await expect(incident.notice).toHaveText('Marked as investigating.')
    await expect(incident.status).toHaveText('Investigating')
    await expect(page.getByTestId('incident-meaning')).toContainText("You're looking into it.")
    await expect(incident.action('investigating')).toBeHidden()

    await incident.action('resolved').click()

    await expect(incident.notice).toHaveText('Marked as resolved.')
    await expect(incident.status).toHaveText('Resolved')
    await expect(incident.action('open')).toHaveText('Reopen')

    await page.reload()
    await expect(incident.status).toHaveText('Resolved')

    await incident.action('open').click()

    await expect(incident.notice).toHaveText('Reopened.')
    await expect(incident.status).toHaveText('Open')
  })

  test('is dismissed, and then no longer listed among the ones that need someone', async ({
    harness,
    incident,
    incidents,
    page,
  }) => {
    await harness.createIncidents([BAD, { address: '8.8.8.8', minutes_ago: 60 }])
    await openIncident(page, ATTACKER)

    await incident.action('dismissed').click()

    await expect(incident.status).toHaveText('Dismissed')
    await incident.back.click()
    await expect(incidents.titles()).toHaveText(['Brute force on ssh (8.8.8.8)'])
    await expect(incidents.count('dismissed')).toHaveText('1')
  })

  test('is in the activity, as a change someone made', async ({
    harness,
    incident,
    activity,
    page,
  }) => {
    await harness.createIncidents([BAD])
    await openIncident(page, ATTACKER)
    await incident.action('resolved').click()
    await expect(incident.status).toHaveText('Resolved')

    await activity.goto()

    await expect(activity.entries.first()).toContainText("An incident's status was changed")
  })

  test('says why a change was not made, and keeps what it has', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([BAD])
    await openIncident(page, ATTACKER)
    await page.route('**/api/incidents/*', (route) =>
      route.request().method() === 'PATCH' ? route.abort() : route.continue(),
    )

    await incident.action('resolved').click()

    await expect(incident.changeError).toBeVisible()
    await expect(incident.status).toHaveText('Open')
    await expect(incident.action('resolved')).toBeEnabled()
  })

  test('says an incident that is not there may have been removed', async ({ incident, page }) => {
    await incident.goto(999_999)

    await expect(incident.error).toContainText('It may have been removed.')
    await expect(incident.retry).toBeHidden()
    await page.getByTestId('back').click()
    await expect(page).toHaveURL('/incidents')
  })

  test('says so when it cannot be loaded, and loads once it can', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([BAD])
    await page.goto('/incidents?view=all')
    const link = await page.getByTestId('incident').first().getAttribute('href')
    await page.route('**/api/incidents/*', (route) => route.abort())

    await page.goto(link ?? '')

    await expect(incident.error).toBeVisible()
    await page.unroute('**/api/incidents/*')
    await incident.retry.click()
    await expect(incident.heading).toHaveText(`Brute force on ssh (${ATTACKER})`)
  })
})
