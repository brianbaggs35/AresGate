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

  test('tells what happened in a sentence, with how sure AresGate is in a ring', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([BAD])

    await openIncident(page, ATTACKER)

    await expect(incident.heroTitle).toHaveText('3 programs agree')
    await expect(incident.heroDetail).toContainText(`reported 7 signals about ${ATTACKER}`)
    await expect(incident.heroDetail).toContainText('An integration banned the address.')
    await expect(incident.heroDetail).toContainText('It involves nas on your network.')
    await expect(incident.score).toContainText('of 100')
    await expect(incident.hero.locator('.hero__arc')).toBeAttached()
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

  test('says why the signals of a bot that came back are one incident', async ({
    harness,
    incident,
    page,
  }) => {
    await harness.createIncidents([
      {
        address: '8.8.4.10',
        scan: true,
        signals: 6,
        neighbours: 2,
        waves: 3,
        ports: [22, 80, 443],
        minutes_ago: 20,
      },
    ])

    await openIncident(page, '8.8.4.10')

    await expect(incident.groupingCard).toContainText('Why these signals are one incident')
    await expect(incident.groupingCard.getByTestId('grouping-activity-scan')).toHaveText('Scanning')
    await expect(incident.waves).toHaveText('3 waves')
    await expect(incident.grouping.first()).toContainText(
      'Signals from 3 addresses of 8.8.4.0/24 doing the same thing are grouped',
    )
    await expect(incident.grouping.nth(2)).toContainText('It came in 3 waves')
    await expect(incident.ports).toHaveText(['22 (SSH)', '80 (HTTP)', '443 (HTTPS)'])
    await expect(incident.signals).toHaveCount(6)
  })

  test('lists a couple of dozen of the ports a sweep touched, and the rest when asked', async ({
    harness,
    incident,
    page,
  }) => {
    const ports = Array.from({ length: 40 }, (_, port) => 1000 + port)
    await harness.createIncidents([{ address: '8.8.4.10', scan: true, signals: 40, ports }])

    await openIncident(page, '8.8.4.10')

    await expect(incident.ports).toHaveCount(24)
    await incident.showMorePorts.click()
    await expect(incident.ports).toHaveCount(40)
    await expect(incident.showMorePorts).toBeHidden()
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

  test.describe('your verdict', () => {
    test('says nothing has been said of it, and offers what it could be about', async ({
      harness,
      incident,
      page,
    }) => {
      await harness.createIncidents([BAD])

      await openIncident(page, ATTACKER)

      await expect(incident.verdictCard).toContainText('Your verdict')
      await expect(incident.standing).toHaveText("You haven't said anything about it yet.")
      await expect(incident.verdictChip).toBeHidden()
      await expect(incident.applied).toHaveCount(0)
      await incident.scope.click()
      await expect(page.getByRole('option').first()).toContainText(ATTACKER)
      await expect(page.getByRole('option')).toHaveCount(1 + 4 + 4)
    })

    test('quiets an address for good: nothing in it counts, and it is no longer listed', async ({
      harness,
      incident,
      incidents,
      page,
    }) => {
      await harness.createIncidents([BAD])
      await openIncident(page, ATTACKER)
      await incident.why.fill('my scanner')

      await incident.give('not_suspicious').click()

      await expect(incident.verdictNotice).toHaveText(`Remembered: ${ATTACKER} is not suspicious.`)
      await expect(incident.verdictChip).toHaveText('Not suspicious')
      await expect(incident.standing).toContainText('will not raise an alarm')
      await expect(incident.confidence).toHaveText('Low confidence')
      await expect(incident.reasons.getByTestId('reason-label')).toHaveText([
        'Left out by your verdicts',
      ])
      await expect(incident.reasons.getByTestId('reason-points')).toHaveText(['0'])
      await expect(incident.signalsTile).toContainText('7 not counted')
      await expect(incident.signals).toHaveCount(7)
      await expect(incident.signals.getByTestId('verdict')).toHaveCount(7)
      await expect(incident.applied).toHaveCount(1)
      await expect(incident.applied).toContainText(ATTACKER)
      await expect(incident.why).toHaveValue('')

      await incident.back.click()
      await expect(incidents.cards).toHaveCount(0)
      await expect(incidents.empty).toContainText('Nothing needs you')
    })

    test('quiets one alert and leaves the rest of the incident counting', async ({
      harness,
      incident,
      page,
    }) => {
      await harness.createIncidents([BAD])
      await openIncident(page, ATTACKER)
      await incident.about(/Brute force on ssh.* From any address/)

      await incident.give('low_priority').click()

      await expect(incident.verdictNotice).toHaveText(
        'Remembered: “Brute force on ssh” is low priority.',
      )
      // Only the first of its signals is that alert, so the rest still count.
      await expect(incident.verdictChip).toBeHidden()
      await expect(incident.standing).toHaveText(
        '1 of its 7 signals match a verdict you gave and are not counted.',
      )
      await expect(incident.signalsTile).toContainText('1 not counted')
      await expect(incident.signals.getByTestId('verdict')).toHaveText(['Low priority'])
      await expect(incident.signals.first().getByTestId('verdict')).toHaveText('Low priority')
    })

    test('is certain of a threat, whatever else it saw', async ({ harness, incident, page }) => {
      await harness.createIncidents([{ address: ATTACKER, severity: 'low', signals: 1 }])
      await openIncident(page, ATTACKER)

      await incident.give('threat').click()

      await expect(incident.verdictChip).toHaveText('Real threat')
      await expect(incident.standing).toHaveText(
        'You said it is a real threat, so AresGate is certain of it.',
      )
      await expect(incident.confidence).toHaveText('High confidence')
      await expect(incident.reasons.getByTestId('reason-label')).toContainText([
        'You said it is a real threat',
      ])
    })

    test('is taken back, and the incident counts again', async ({ harness, incident, page }) => {
      await harness.createIncidents([BAD])
      await harness.createVerdicts([{ verdict: 'not_suspicious', address: ATTACKER }])
      await page.goto('/incidents?quieted=1')
      await page.getByTestId('incident').click()
      await expect(incident.verdictChip).toHaveText('Not suspicious')

      await incident.applied.getByTestId('take-back').click()

      await expect(incident.verdictNotice).toHaveText(`Taken back: ${ATTACKER}.`)
      await expect(incident.verdictChip).toBeHidden()
      await expect(incident.standing).toHaveText("You haven't said anything about it yet.")
      await expect(incident.confidence).toHaveText('High confidence')
      await expect(incident.applied).toHaveCount(0)
    })

    test('says why a verdict was not remembered, and keeps what it has', async ({
      harness,
      incident,
      page,
    }) => {
      await harness.createIncidents([BAD])
      await openIncident(page, ATTACKER)
      await page.route('**/api/verdicts', (route) =>
        route.request().method() === 'POST' ? route.abort() : route.continue(),
      )

      await incident.give('not_suspicious').click()

      await expect(incident.verdictError).toBeVisible()
      await expect(incident.verdictChip).toBeHidden()
      await expect(incident.give('not_suspicious')).toBeEnabled()
    })

    test('is on the Settings page once given, to review it there', async ({
      harness,
      incident,
      page,
      verdicts,
    }) => {
      await harness.createIncidents([BAD])
      await openIncident(page, ATTACKER)
      await incident.why.fill('my scanner')
      await incident.give('not_suspicious').click()
      await expect(incident.verdictNotice).toBeVisible()

      await verdicts.goto()

      await expect(verdicts.rows).toHaveCount(1)
      await expect(verdicts.about()).toHaveText([ATTACKER])
      await expect(verdicts.rows.first().getByTestId('verdict-why')).toHaveText('Why: my scanner')
    })
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
