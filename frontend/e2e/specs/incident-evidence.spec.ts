import type { Page } from '@playwright/test'

import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const ATTACKER = '93.184.216.34'

/** An ssh brute force that Wazuh and ntopng reported, and that OPNsense reported every alert of
 * again a couple of seconds later, each saying what it knows besides the basics. */
const SAID: IncidentRequest = {
  address: ATTACKER,
  severity: 'high',
  programs: ['wazuh', 'ntopng'],
  signals: 4,
  twin: 'opnsense',
  detailed: true,
  minutes_ago: 5,
}

async function openIncident(page: Page): Promise<void> {
  await page.goto('/incidents?view=all')
  await page.getByTestId('incident').filter({ hasText: ATTACKER }).click()
  await expect(page).toHaveURL(/\/incidents\/\d+$/)
}

test.describe('what the programs said of an incident', () => {
  test('adds up what each program knew, once for every alert', async ({ harness, page }) => {
    await harness.createIncidents([SAID])

    await openIncident(page)

    const card = page.getByTestId('insights-card')
    await expect(card).toBeVisible()
    // Every program that reported part of it, the one that reported most first.
    await expect(card.getByTestId('insight-program-name')).toHaveText([
      'OPNsense',
      'ntopng',
      'Wazuh',
    ])
    await expect(card.getByTestId('insight-techniques')).toContainText('T1110 Brute Force')
    await expect(card.getByTestId('insight-techniques')).toContainText('Credential Access')
    await expect(card.getByTestId('insight-hosts')).toContainText('web-server')
    await expect(card.getByTestId('insight-apps')).toContainText('ssh')
    await expect(card.getByTestId('insight-named-hostname')).toContainText('scanner.example.net')
    await expect(card.getByTestId('insight-tags')).toContainText('authentication_failed')
  })

  test('names the programs that saw the same alert, and shows what each of them said', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([SAID])

    await openIncident(page)

    const first = page.getByTestId('occurrence').first()
    // OPNsense's reports are Wazuh's alerts seen twice, so they are not alerts of their own.
    await expect(first.getByTestId('occurrence-duplicates')).toContainText(
      'also reported by OPNsense, counted once',
    )
    await expect(
      first.getByTestId('occurrence-report').getByRole('heading', { level: 3 }),
    ).toHaveText(['Wazuh', 'OPNsense'])
    const wazuh = first.getByTestId('occurrence-report').first()
    await expect(wazuh.getByTestId('evidence-host')).toHaveText('web-server (192.168.1.20)')
    await expect(wazuh.getByTestId('evidence-facts')).toContainText('5760')
    await expect(wazuh.getByTestId('evidence-mitre')).toContainText('T1110')
    await expect(wazuh.getByTestId('evidence-excerpt')).toContainText('Failed password for root')
    const suricata = first.getByTestId('occurrence-report').nth(1)
    await expect(suricata.getByTestId('evidence-traffic')).toContainText('Sent: 14')
    await expect(suricata.getByTestId('evidence-app')).toHaveText('ssh')
  })

  test('draws who talked to whom, with what each program knows of both ends', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([SAID])

    await openIncident(page)

    const card = page.getByTestId('conversations-card')
    await expect(card).toBeVisible()
    const talk = card.getByTestId('conversation').first()
    // ntopng says who the flow was between and what it was; Wazuh and OPNsense add their own.
    const client = talk.getByTestId('end-client')
    await expect(client.getByTestId('end-title')).toHaveText(ATTACKER)
    await expect(client.getByTestId('end-location')).toHaveText('On the internet')
    await expect(client.getByTestId('end-country')).toContainText('Netherlands')
    await expect(client.getByTestId('end-blacklisted')).toHaveText('On a blacklist')
    const server = talk.getByTestId('end-server')
    await expect(server.getByTestId('end-title')).toHaveText('web-server')
    await expect(server.getByTestId('end-location')).toHaveText('On your network')
    await expect(server.getByTestId('end-port')).toContainText('port 22 (ssh)')
    await expect(talk.getByTestId('conversation-over')).toContainText('SSH')
    await expect(talk.getByTestId('conversation-volume')).toContainText('Sent 3.2 KB')
    await expect(talk.getByTestId('conversation-duration')).toHaveText('Lasted 1 min 1 s')
    await expect(talk.getByTestId('conversation-programs')).toContainText('ntopng')
  })

  test('shows ntopng’s own words, its score and the flow it described', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([SAID])

    await openIncident(page)

    const ntopng = page
      .getByTestId('occurrence')
      .filter({ hasText: 'ntopng' })
      .getByTestId('occurrence-report')
      .first()
    await expect(ntopng.getByTestId('evidence-summary')).toContainText('Many failed logins')
    await expect(ntopng.getByTestId('evidence-score')).toHaveText('Its own score: 100')
    await expect(ntopng.getByTestId('evidence-flow')).toContainText('web-server, port 22 (ssh)')
    await expect(ntopng.getByTestId('evidence-duration')).toHaveText('Lasted 1 min 1 s')
  })

  test('shows what was sent where the firewall kept the packet', async ({ harness, page }) => {
    await harness.createIncidents([SAID])

    await openIncident(page)

    await expect(page.getByTestId('evidence-payload').first()).toContainText('SSH-2.0-libssh_0.9.6')
  })

  test('says what connecting the programs that are not connected would add', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([SAID])

    await openIncident(page)

    const card = page.getByTestId('coverage-card')
    await expect(card).toBeVisible()
    await expect(card.getByTestId('coverage-seen').getByTestId('coverage-name')).toHaveText([
      'ntopng',
      'OPNsense',
      'Wazuh',
    ])
    await expect(card.getByTestId('coverage-missing').first()).toContainText('Not connected')
    await card.getByTestId('coverage-connect-wazuh').click()
    await expect(page).toHaveURL(/\/integrations\/wazuh$/)
  })

  test('opens and closes what each program said', async ({ harness, page }) => {
    await harness.createIncidents([SAID])
    await openIncident(page)
    const first = page.getByTestId('occurrence').first()
    const toggle = first.getByTestId('occurrence-toggle')

    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(first.getByTestId('occurrence-reports')).toBeHidden()

    await toggle.click()
    await expect(first.getByTestId('occurrence-reports')).toBeVisible()
  })

  test('has no card for programs that said nothing more than the basics', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([
      { address: ATTACKER, severity: 'high', programs: ['wazuh'], signals: 1 },
    ])

    await openIncident(page)

    await expect(page.getByTestId('incident-hero')).toBeVisible()
    await expect(page.getByTestId('insights-card')).toHaveCount(0)
  })
})
