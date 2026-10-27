import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const ATTACKER = '93.184.216.34'

/** Four attacks in each of the states the list tells apart: a bad one that is open and banned, a
 * serious one, one being looked at and one that is over. The last signal of each is newer than
 * the one after it, which is the order they are listed in. */
const SOME: IncidentRequest[] = [
  {
    address: ATTACKER,
    severity: 'critical',
    programs: ['wazuh', 'opnsense', 'crowdsec'],
    signals: 6,
    ban: true,
    minutes_ago: 4,
    device_name: 'nas',
  },
  {
    address: '8.8.8.8',
    severity: 'high',
    programs: ['wazuh', 'opnsense'],
    signals: 3,
    minutes_ago: 35,
  },
  {
    address: '1.1.1.1',
    severity: 'medium',
    programs: ['ntopng'],
    signals: 1,
    minutes_ago: 180,
    status: 'investigating',
  },
  {
    address: '9.9.9.9',
    severity: 'low',
    programs: ['opnsense'],
    signals: 2,
    minutes_ago: 400,
    status: 'resolved',
  },
]

const title = (address: string) => `Brute force on ssh (${address})`

test.describe('incidents', () => {
  test('are in the menu, and say none have been made yet on a new install', async ({
    page,
    shell,
    incidents,
  }) => {
    await page.goto('/')

    await shell.incidentsLink.click()

    await expect(page).toHaveURL('/incidents')
    await expect(page).toHaveTitle('Incidents · AresGate')
    await expect(incidents.heading).toHaveText('Incidents')
    await expect(shell.incidentsLink).toHaveAttribute('aria-current', 'page')
    await expect(incidents.empty).toContainText('No incidents yet')
    await incidents.empty.getByRole('link', { name: 'See your integrations' }).click()
    await expect(page).toHaveURL('/integrations')
  })

  test('list the ones that are not over, the one that was last heard from first', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(SOME)

    await incidents.goto()

    await expect(incidents.titles()).toHaveText([
      title(ATTACKER),
      title('8.8.8.8'),
      title('1.1.1.1'),
    ])
    await expect(incidents.view('active')).toHaveClass(/v-btn--active/)
    await expect(incidents.updated).toContainText('Updated')
  })

  test('say how serious each is, how sure AresGate is and what saw it', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(SOME)

    await incidents.goto()

    const worst = incidents.cards.first()
    await expect(worst.getByTestId('severity')).toHaveText('Critical')
    await expect(worst.getByTestId('incident-banned')).toBeVisible()
    await expect(worst.getByTestId('confidence-level')).toHaveText('High confidence')
    await expect(worst.getByTestId('incident-signals')).toContainText('7 signals')
    await expect(worst.getByTestId('incident-programs')).toHaveText(
      'Seen by CrowdSec, OPNsense, Wazuh',
    )
    await expect(worst.getByTestId('incident-subject')).toContainText(ATTACKER)
    const other = incidents.cards.nth(2)
    await expect(other.getByTestId('incident-status')).toHaveText('Investigating')
    await expect(other.getByTestId('confidence-level')).toHaveText('Low confidence')
  })

  test('show a bot that swept from a block in waves as one incident, and say how', async ({
    harness,
    incidents,
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

    await incidents.goto()

    await expect(incidents.cards).toHaveCount(1)
    const sweep = incidents.cards.first()
    await expect(sweep.getByTestId('incident-activity-scan')).toHaveText('Scanning')
    await expect(sweep.getByTestId('incident-signals')).toContainText('6 signals')
    await expect(sweep.getByTestId('incident-waves')).toHaveText('3 waves')
    await expect(sweep.getByTestId('incident-ports')).toHaveText('3 ports')
    await expect(sweep.getByTestId('incident-neighbours')).toHaveText('2 neighbouring addresses')
  })

  test('keep the same bot hours later as another incident', async ({ harness, incidents }) => {
    const scan = { address: '8.8.4.10', scan: true, signals: 3 }
    await harness.createIncidents([
      { ...scan, minutes_ago: 600 },
      { ...scan, minutes_ago: 10 },
    ])

    await incidents.goto('?view=all')

    await expect(incidents.cards).toHaveCount(2)
  })

  test('count the incidents in each view, and show the others when asked', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()

    await expect(incidents.count('active')).toHaveText('3')
    await expect(incidents.count('open')).toHaveText('2')
    await expect(incidents.count('investigating')).toHaveText('1')
    await expect(incidents.count('resolved')).toHaveText('1')
    await expect(incidents.count('dismissed')).toHaveText('0')
    await expect(incidents.count('all')).toHaveText('4')

    await incidents.view('resolved').click()

    await expect(page).toHaveURL('/incidents?view=resolved')
    await expect(incidents.titles()).toHaveText([title('9.9.9.9')])

    await incidents.view('all').click()
    await expect(incidents.titles()).toHaveCount(4)

    await incidents.view('active').click()
    await expect(page).toHaveURL('/incidents')
    await expect(incidents.titles()).toHaveCount(3)
  })

  test('say nothing needs anyone when every one is over, and offer them', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents([
      { address: ATTACKER, status: 'resolved' },
      { address: '8.8.8.8', status: 'dismissed' },
    ])

    await incidents.goto()

    await expect(incidents.empty).toContainText('Nothing needs you')
    await expect(incidents.empty).toContainText('2 in all')
    await incidents.empty.getByRole('button', { name: 'Show all incidents' }).click()
    await expect(incidents.titles()).toHaveCount(2)
  })

  test('are narrowed to the serious ones, and the ones AresGate is sure of', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()

    await incidents.choose(incidents.severity, 'High or more')

    await expect(page).toHaveURL('/incidents?severity=high')
    await expect(incidents.titles()).toHaveText([title(ATTACKER), title('8.8.8.8')])

    await incidents.choose(incidents.confidence, 'High only')

    await expect(page).toHaveURL('/incidents?severity=high&confidence=65')
    await expect(incidents.titles()).toHaveText([title(ATTACKER)])
  })

  test('are searched by an address', async ({ harness, incidents, page }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()

    await incidents.search('8.8.8.8')

    await expect(page).toHaveURL('/incidents?q=8.8.8.8')
    await expect(incidents.titles()).toHaveText([title('8.8.8.8')])
    await expect(incidents.terms).toHaveText(['Address: 8.8.8.8'])
  })

  test('are searched in words, which are shown as terms that each come off with a tap', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()

    await incidents.search('severity>=high -address:8.8.8.8')

    await expect(page).toHaveURL('/incidents?q=severity%3E=high+-address:8.8.8.8')
    await expect(incidents.titles()).toHaveText([title(ATTACKER)])
    await expect(incidents.terms).toHaveText(['Severity: at least high', 'Not address: 8.8.8.8'])

    await incidents.terms.nth(1).click()

    await expect(incidents.titles()).toHaveText([title(ATTACKER), title('8.8.8.8')])
    await expect(incidents.terms).toHaveText(['Severity: at least high'])
    await expect(incidents.searchBox).toHaveValue('severity>=high')
  })

  test('are searched for what they were reported by, how long ago and the device', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()

    await incidents.search('source:ntopng')
    await expect(incidents.titles()).toHaveText([title('1.1.1.1')])

    await incidents.search('since:1h')
    await expect(incidents.titles()).toHaveText([title(ATTACKER), title('8.8.8.8')])

    // The device that was attacked is the same in all of them.
    await incidents.search('device:nas')
    await expect(incidents.titles()).toHaveCount(3)
    await incidents.search('device:printer')
    await expect(incidents.empty).toContainText('Nothing matches')
  })

  test('look across every status for a search that names one', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()

    await incidents.search('status:resolved')

    await expect(page).toHaveURL('/incidents?view=all&q=status:resolved')
    await expect(incidents.view('all')).toHaveClass(/v-btn--active/)
    await expect(incidents.titles()).toHaveText([title('9.9.9.9')])
  })

  test('say why a search can not be understood, and keep what was listed', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()
    await expect(incidents.titles()).toHaveCount(3)

    await incidents.search('sevrity:high')

    await expect(incidents.searchField).toContainText('Did you mean "severity"?')
    await expect(incidents.titles()).toHaveCount(3)
    await expect(incidents.terms).toHaveCount(0)

    await incidents.search('severity:high')

    await expect(incidents.searchField).not.toContainText('Did you mean')
    await expect(incidents.titles()).toHaveText([title('8.8.8.8')])
  })

  test('summarise what was found, and narrow it with a tap on a severity or an integration', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()
    await expect(incidents.facet('severity:critical')).toHaveText('Critical1')
    await expect(incidents.facet('source:wazuh')).toHaveText('Wazuh2')
    await expect(incidents.facet('severity:low')).toHaveCount(0)

    await incidents.facet('source:opnsense').click()

    await expect(page).toHaveURL('/incidents?q=source:opnsense')
    await expect(incidents.facet('source:opnsense')).toHaveAttribute('aria-pressed', 'true')
    await expect(incidents.titles()).toHaveText([title(ATTACKER), title('8.8.8.8')])

    await incidents.facet('severity:high').click()
    await expect(incidents.titles()).toHaveText([title('8.8.8.8')])

    await incidents.facet('source:opnsense').click()
    await expect(page).toHaveURL('/incidents?q=severity:high')
  })

  test('show how to search, and the searches made before, and are reached with the slash key', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()
    await expect(incidents.titles()).toHaveCount(3)

    await page.keyboard.press('/')
    await expect(incidents.searchBox).toBeFocused()
    await incidents.searchBox.press('Enter')

    await incidents.search('port:22')
    await incidents.search('source:wazuh')
    await incidents.searchHelp.click()
    await expect(incidents.searchPanel).toBeVisible()
    await expect(incidents.recent).toHaveText(['source:wazuh', 'port:22'])

    await incidents.recent.last().click()

    await expect(incidents.searchPanel).toBeHidden()
    await expect(incidents.searchBox).toHaveValue('port:22')
    await expect(incidents.terms).toHaveText(['Port: 22'])

    await incidents.searchHelp.click()
    await page.getByTestId('search-example').first().click()
    await expect(incidents.searchBox).toHaveValue(/^port:22 \S/)
  })

  test('keep a search under a name, and use it again from the panel', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()
    await expect(incidents.titles()).toHaveCount(3)

    await incidents.search('source:wazuh')
    await incidents.searchHelp.click()
    await incidents.saved.keep('From Wazuh')
    await expect(incidents.saved.notice).toHaveText('Saved as From Wazuh.')

    await incidents.goto()
    await expect(incidents.titles()).toHaveCount(3)
    await incidents.searchHelp.click()
    await incidents.saved.rows.first().click()

    await expect(incidents.searchBox).toHaveValue('source:wazuh')
    await expect(incidents.terms).toHaveCount(1)
    await expect(incidents.titles()).toHaveCount(2)
  })

  test('say nothing matches when the choices leave none, and drop them when asked', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()

    await incidents.search('203.0.113.77')

    await expect(incidents.empty).toContainText('Nothing matches')
    await incidents.empty.getByRole('button', { name: 'Clear filters' }).click()
    await expect(page).toHaveURL('/incidents')
    await expect(incidents.titles()).toHaveCount(3)
    await expect(incidents.clear).toBeHidden()
  })

  test('keep the choices in the address of the page, so a link brings them back', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)

    await incidents.goto('?view=all&severity=medium&q=source%3Aopnsense%2Cntopng')

    await expect(incidents.view('all')).toHaveClass(/v-btn--active/)
    await expect(incidents.titles()).toHaveText([
      title(ATTACKER),
      title('8.8.8.8'),
      title('1.1.1.1'),
    ])
    await page.reload()
    await expect(incidents.titles()).toHaveCount(3)
    await expect(incidents.clear).toBeVisible()
  })

  test('are listed a page at a time, with a button for the next', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents(
      Array.from({ length: 27 }, (_, number) => ({
        // Each from a block of its own: addresses side by side are one bot.
        address: `20.20.${(number + 1).toString()}.20`,
        minutes_ago: number + 1,
      })),
    )

    await incidents.goto()

    await expect(incidents.cards).toHaveCount(25)
    await expect(incidents.more).toContainText('Showing 25 of 27.')
    await expect(incidents.showMore).toHaveText('Show 2 more')

    await incidents.showMore.click()

    await expect(incidents.cards).toHaveCount(27)
    await expect(incidents.more).toBeHidden()
  })

  test('lead to the page of the incident that is chosen', async ({ harness, incidents, page }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()

    await incidents.cards.nth(1).click()

    await expect(page).toHaveURL(/\/incidents\/\d+$/)
    await expect(page.getByTestId('page-heading')).toHaveText(title('8.8.8.8'))
  })

  test('ask again by the button, and keep what they have when that fails', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(3)
    await page.route('**/api/incidents?**', (route) => route.abort())

    await incidents.refresh.click()

    await expect(incidents.stale).toContainText('What is shown is from')
    await expect(incidents.cards).toHaveCount(3)
  })

  test('say so when they cannot be loaded at all, and load once they can', async ({
    harness,
    incidents,
    page,
  }) => {
    await harness.createIncidents(SOME)
    await page.route('**/api/incidents?**', (route) => route.abort())

    await incidents.goto()

    await expect(incidents.error).toBeVisible()
    await page.unroute('**/api/incidents?**')
    await incidents.retry.click()
    await expect(incidents.cards).toHaveCount(3)
  })

  test.describe('and your verdicts', () => {
    test('leave out the ones you called not suspicious, and offer them with a count', async ({
      harness,
      incidents,
    }) => {
      await harness.createIncidents(SOME)
      await harness.createVerdicts([{ verdict: 'not_suspicious', address: '8.8.8.8' }])

      await incidents.goto()

      await expect(incidents.titles()).toHaveText([title(ATTACKER), title('1.1.1.1')])
      await expect(incidents.quieted).toContainText('Show 1 quieted by your verdicts')
      // The counts on the views are of what is listed, so they add up to the cards.
      await expect(incidents.count('open')).toHaveText('1')
    })

    test('list them again once asked, saying what was said of them, and keep that in the address', async ({
      harness,
      incidents,
      page,
    }) => {
      await harness.createIncidents(SOME)
      await harness.createVerdicts([{ verdict: 'low_priority', address: '8.8.8.8' }])
      await incidents.goto()

      await incidents.quieted.getByRole('checkbox').check()

      await expect(page).toHaveURL(/quieted=1/)
      await expect(incidents.cards).toHaveCount(3)
      await expect(
        incidents.cards.filter({ hasText: '8.8.8.8' }).getByTestId('verdict'),
      ).toHaveText('Low priority')

      await page.reload()
      await expect(incidents.cards).toHaveCount(3)
      await incidents.clear.click()
      await expect(incidents.cards).toHaveCount(2)
    })

    test('say a real threat is a real threat, however weak the signals were', async ({
      harness,
      incidents,
    }) => {
      await harness.createIncidents([{ address: '9.9.9.9', severity: 'low', signals: 1 }])
      await harness.createVerdicts([{ verdict: 'threat', address: '9.9.9.9' }])

      await incidents.goto()

      await expect(incidents.cards).toHaveCount(1)
      await expect(incidents.cards.getByTestId('verdict')).toHaveText('Real threat')
      await expect(incidents.cards.getByTestId('confidence-level')).toHaveText('High confidence')
    })

    test('say nothing needs you when every incident is one you quieted, and offer them', async ({
      harness,
      incidents,
    }) => {
      await harness.createIncidents([{ address: ATTACKER }])
      await harness.createVerdicts([{ verdict: 'not_suspicious', address: ATTACKER }])

      await incidents.goto()

      await expect(incidents.empty).toContainText('Nothing needs you')
      await expect(incidents.empty).toContainText('1 is hidden.')
      await incidents.showQuieted.click()
      await expect(incidents.cards).toHaveCount(1)
      await expect(incidents.cards.getByTestId('verdict')).toHaveText('Not suspicious')
    })
  })
})
