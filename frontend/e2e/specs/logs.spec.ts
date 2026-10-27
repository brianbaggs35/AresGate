import type { EventRequest } from '../support'
import { expect, test } from '../support'

const SCANNER = '203.0.113.7'
const NAS = '192.168.1.20'

/** Four events from three integrations, the newest first as the page lists them: a blocked
 * connection, a failed login, a scan alert whose record was not kept and a flow. */
const SOME: EventRequest[] = [
  {
    source: 'opnsense',
    kind: 'firewall',
    severity: 'info',
    summary: `Blocked tcp from ${SCANNER}`,
    src_address: SCANNER,
    src_port: 51234,
    dst_address: NAS,
    dst_port: 443,
    protocol: 'tcp',
    seconds_ago: 60,
    raw: { action: 'block', interface: 'wan', dir: 'in', reason: 'match', proto: 'tcp' },
  },
  {
    source: 'wazuh',
    kind: 'alert',
    severity: 'high',
    summary: 'sshd: Failed password for root',
    signature: '5710 sshd: Attempt to login using a non-existent user',
    src_address: SCANNER,
    dst_address: NAS,
    dst_port: 22,
    protocol: 'tcp',
    seconds_ago: 120,
    raw: {
      rule: { id: '5710', level: 5, firedtimes: 3 },
      agent: { name: 'nas', id: '001' },
      full_log: `Oct 27 09:01:02 nas sshd[411]: Failed password for root from ${SCANNER} port 51234 ssh2`,
    },
  },
  {
    source: 'opnsense',
    kind: 'alert',
    severity: 'medium',
    summary: 'ET SCAN Potential SSH Scan',
    signature: 'ET SCAN Potential SSH Scan',
    src_address: SCANNER,
    dst_address: NAS,
    dst_port: 22,
    protocol: 'tcp',
    seconds_ago: 180,
  },
  {
    source: 'ntopng',
    kind: 'flow',
    severity: 'low',
    summary: 'Long flow to 198.51.100.4',
    src_address: NAS,
    dst_address: '198.51.100.4',
    dst_port: 8080,
    protocol: 'tcp',
    seconds_ago: 240,
    raw: { bytes: 1_200_000, duration: 5400 },
  },
]

const FIREWALL = `Blocked tcp from ${SCANNER}`
const FAILED_LOGIN = 'sshd: Failed password for root'
const SCAN = 'ET SCAN Potential SSH Scan'

test.describe('logs', () => {
  test('are in the menu, and say none have been collected yet on a new install', async ({
    page,
    shell,
    logs,
  }) => {
    await page.goto('/')

    await shell.logsLink.click()

    await expect(page).toHaveURL('/logs')
    await expect(page).toHaveTitle('Logs · AresGate')
    await expect(logs.heading).toHaveText('Logs')
    await shell.expectCurrent('logs')
    await expect(logs.empty).toContainText('No events yet')
    await expect(logs.emptyIntegrations).toBeVisible()
    await expect(logs.live).toHaveAttribute('aria-pressed', 'true')
  })

  test('list every event, the newest first, with what each says', async ({ harness, logs }) => {
    await harness.createEvents(SOME)

    await logs.goto()

    await expect(logs.events).toHaveCount(4)
    await expect(logs.events.nth(0)).toContainText(FIREWALL)
    await expect(logs.events.nth(1)).toContainText(FAILED_LOGIN)
    await expect(logs.events.nth(2)).toContainText(SCAN)
    await expect(logs.events.nth(3)).toContainText('Long flow to 198.51.100.4')
    await expect(logs.matched).toHaveText('4 events')
    await expect(logs.updated).toContainText('asks for new events every 5 seconds')
  })

  test('say how serious each is, what reported it and where it went', async ({ harness, logs }) => {
    await harness.createEvents(SOME)
    await logs.goto()

    const failed = logs.open(FAILED_LOGIN)

    await expect(failed).toContainText('High')
    await expect(failed).toContainText('Wazuh')
    await expect(failed).toContainText(`${NAS}:22`)
    await expect(logs.open(FIREWALL)).toContainText('OPNsense')
  })

  test('spread across the severities, the integrations and the kinds, with a tap to narrow', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SOME)
    await logs.goto()
    await expect(logs.facets).toBeVisible()

    await logs.facet('kind:alert').click()

    await expect(page).toHaveURL(/q=kind:alert/)
    await expect(logs.events).toHaveCount(2)
    await expect(logs.matched).toHaveText('2 events')
    await expect(logs.searchBox).toHaveValue('kind:alert')

    await logs.facet('source:wazuh').click()

    await expect(logs.events).toHaveCount(1)
    await expect(logs.events.first()).toContainText(FAILED_LOGIN)

    // A second tap on the same choice takes it off.
    await logs.facet('source:wazuh').click()
    await expect(logs.events).toHaveCount(2)
  })

  test('are searched in words, which are shown as terms that each come off with a tap', async ({
    harness,
    logs,
  }) => {
    await harness.createEvents(SOME)
    await logs.goto()

    await logs.search('severity>=low -port:22')

    await expect(logs.terms).toHaveCount(2)
    await expect(logs.events).toHaveCount(1)
    await expect(logs.events.first()).toContainText('Long flow')

    await logs.terms.last().click()

    await expect(logs.searchBox).toHaveValue('severity>=low')
    await expect(logs.events).toHaveCount(3)
  })

  test('are searched by an address, a rule and the words an event says', async ({
    harness,
    logs,
  }) => {
    await harness.createEvents(SOME)
    await logs.goto()

    await logs.search('198.51.100.4')
    await expect(logs.events).toHaveCount(1)
    await expect(logs.events.first()).toContainText('Long flow')

    await logs.search('signature:"ET SCAN"')
    await expect(logs.events).toHaveCount(1)
    await expect(logs.events.first()).toContainText(SCAN)

    await logs.search('"failed password"')
    await expect(logs.events).toHaveCount(1)
    await expect(logs.events.first()).toContainText(FAILED_LOGIN)

    await logs.search(`from:${NAS}`)
    await expect(logs.events).toHaveCount(1)
    await expect(logs.events.first()).toContainText('Long flow')
  })

  test('are searched through the record each integration sent', async ({ harness, logs }) => {
    await harness.createEvents(SOME)
    await logs.goto()

    await logs.search('raw:firedtimes since:1h')

    await expect(logs.events).toHaveCount(1)
    await expect(logs.events.first()).toContainText(FAILED_LOGIN)
  })

  test('say why a search can not be understood, and keep what was listed', async ({
    harness,
    logs,
  }) => {
    await harness.createEvents(SOME)
    await logs.goto()
    await expect(logs.events).toHaveCount(4)

    await logs.search('sevrity:high')

    await expect(logs.searchField).toContainText('Did you mean "severity"?')
    await expect(logs.searchStale).toBeVisible()
    await expect(logs.events).toHaveCount(4)

    await logs.search('severity:high')

    await expect(logs.searchField).not.toContainText('Did you mean')
    await expect(logs.searchStale).toBeHidden()
    await expect(logs.events).toHaveCount(1)
  })

  test('say nothing matches when a search finds none, and drop it when asked', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SOME)
    await logs.goto()

    await logs.search('198.51.100.99')

    await expect(logs.empty).toContainText('Nothing matches')
    await expect(logs.events).toHaveCount(0)

    await logs.emptyClear.click()

    await expect(page).toHaveURL('/logs')
    await expect(logs.events).toHaveCount(4)
    await expect(logs.searchBox).toHaveValue('')
  })

  test('keep the search in the address of the page, so a link brings it back', async ({
    harness,
    logs,
  }) => {
    await harness.createEvents(SOME)

    await logs.goto('?q=source%3Awazuh')

    await expect(logs.searchBox).toHaveValue('source:wazuh')
    await expect(logs.terms).toHaveCount(1)
    await expect(logs.events).toHaveCount(1)
  })

  test('show how to search, and the searches made before, and are reached with the slash key', async ({
    harness,
    logs,
    page,
  }) => {
    await harness.createEvents(SOME)
    await logs.goto()
    await expect(logs.events).toHaveCount(4)

    await page.keyboard.press('/')
    await expect(logs.searchBox).toBeFocused()

    await logs.search('port:22')
    await logs.search('source:wazuh')
    await logs.searchHelp.click()
    await expect(logs.searchPanel).toBeVisible()
    await expect(logs.recent).toHaveText(['source:wazuh', 'port:22'])

    await logs.recent.last().click()

    await expect(logs.searchPanel).toBeHidden()
    await expect(logs.searchBox).toHaveValue('port:22')
    await expect(logs.events).toHaveCount(2)
  })

  test.describe('and the sheet for one', () => {
    test('opens with what is known of it, and the record the integration sent', async ({
      harness,
      logs,
    }) => {
      await harness.createEvents(SOME)
      await logs.goto()

      await logs.open(FAILED_LOGIN).click()

      await expect(logs.drawer).toBeVisible()
      await expect(logs.drawerTitle).toHaveText(FAILED_LOGIN)
      await expect(logs.field('severity')).toContainText('High')
      await expect(logs.field('source')).toContainText('Wazuh')
      await expect(logs.field('kind')).toContainText('alert')
      await expect(logs.field('from')).toContainText(SCANNER)
      await expect(logs.field('to')).toContainText(NAS)
      await expect(logs.field('to-port')).toContainText('22')
      await expect(logs.field('protocol')).toContainText('tcp')
      await expect(logs.field('signature')).toContainText('5710 sshd')
      await expect(logs.rawText).toContainText('"firedtimes": 3')
      await expect(logs.rawText).toContainText('Failed password for root from')
      await expect(logs.drawerNoIncident).toHaveText('Not part of an incident.')
    })

    test('says so when the integration kept no record', async ({ harness, logs }) => {
      await harness.createEvents(SOME)
      await logs.goto()

      await logs.open(SCAN).click()

      await expect(logs.drawerTitle).toHaveText(SCAN)
      await expect(logs.rawNone).toContainText('did not send a record')
      await expect(logs.rawText).toHaveCount(0)
    })

    test('closes with its button and with Escape, and the list stays where it was', async ({
      harness,
      logs,
      page,
    }) => {
      await harness.createEvents(SOME)
      await logs.goto()

      await logs.open(FIREWALL).click()
      await expect(logs.drawer).toBeVisible()
      await logs.drawerClose.click()
      await expect(logs.drawer).toBeHidden()

      await logs.open(FIREWALL).click()
      await expect(logs.drawer).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(logs.drawer).toBeHidden()
      await expect(logs.events).toHaveCount(4)
    })

    test('goes to the older and the newer event, by the buttons and by j and k', async ({
      harness,
      logs,
    }) => {
      await harness.createEvents(SOME)
      await logs.goto()
      await logs.open(FIREWALL).click()
      await expect(logs.drawerNewer).toBeDisabled()

      await logs.drawerOlder.click()
      await expect(logs.drawerTitle).toHaveText(FAILED_LOGIN)

      await logs.drawer.press('j')
      await expect(logs.drawerTitle).toHaveText(SCAN)

      await logs.drawer.press('k')
      await expect(logs.drawerTitle).toHaveText(FAILED_LOGIN)

      await logs.drawerNewer.click()
      await expect(logs.drawerTitle).toHaveText(FIREWALL)
      await expect(logs.drawerNewer).toBeDisabled()
    })

    test('copies a value, and says that it did', async ({ context, harness, logs, page }) => {
      await context.grantPermissions(['clipboard-read', 'clipboard-write'])
      await harness.createEvents(SOME)
      await logs.goto()
      await logs.open(FAILED_LOGIN).click()

      await logs.field('from').getByTestId('copy').click()

      await expect(logs.field('from').getByTestId('copy-said')).toBeVisible()
      expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(SCANNER)
    })

    test('copies the whole record', async ({ context, harness, logs, page }) => {
      await context.grantPermissions(['clipboard-read', 'clipboard-write'])
      await harness.createEvents(SOME)
      await logs.goto()
      await logs.open(FAILED_LOGIN).click()

      await logs.rawRecord.getByTestId('copy').click()

      const copied = await page.evaluate(() => navigator.clipboard.readText())
      expect(JSON.parse(copied)).toMatchObject({ rule: { id: '5710' }, agent: { name: 'nas' } })
    })

    test('looks for the events like a field of it, and closes to show them', async ({
      harness,
      logs,
      page,
    }) => {
      await harness.createEvents(SOME)
      await logs.goto()
      await logs.open(FAILED_LOGIN).click()

      await logs.find('source').click()

      await expect(logs.drawer).toBeHidden()
      await expect(page).toHaveURL(/q=source:wazuh/)
      await expect(logs.events).toHaveCount(1)
    })

    test('links to every event with an address it names', async ({ harness, logs, page }) => {
      await harness.createEvents(SOME)
      await logs.goto()
      await logs.open(FAILED_LOGIN).click()
      await expect(logs.drawerAddresses.getByRole('link')).toHaveCount(2)

      await logs.drawerAddresses.getByRole('link', { name: new RegExp(NAS) }).click()

      await expect(page).toHaveURL(/q=address:192\.168\.1\.20/)
      await expect(logs.drawer).toBeHidden()
      await expect(logs.events).toHaveCount(4)
    })

    test('leads to the incident an event was filed into', async ({ harness, logs, page }) => {
      await harness.createIncidents([{ address: '93.184.216.34', programs: ['wazuh'], signals: 2 }])
      await logs.goto()
      await expect(logs.events).toHaveCount(2)

      await logs.events.first().click()
      await expect(logs.drawerIncident).toContainText('Filed in an incident')
      await logs.drawerIncident.click()

      await expect(page).toHaveURL(/\/incidents\/\d+$/)
    })
  })

  test('are listed a page at a time, with a button for the older', async ({ harness, logs }) => {
    await harness.createEvents([{ summary: 'Blocked udp', repeat: 130, every_seconds: 20 }])

    await logs.goto()

    await expect(logs.events).toHaveCount(100)
    await expect(logs.more).toContainText('Showing 100 of 130.')

    await logs.showOlder.click()

    await expect(logs.events).toHaveCount(130)
    await expect(logs.more).toBeHidden()
  })

  test.describe('live', () => {
    test('follow along as events come in', async ({ harness, logs }) => {
      await harness.createEvents(SOME)
      await logs.goto()
      await expect(logs.events).toHaveCount(4)

      await harness.createEvents([
        { source: 'crowdsec', kind: 'decision', summary: 'Banned 203.0.113.9', seconds_ago: 0 },
      ])

      await expect(logs.events).toHaveCount(5, { timeout: 15_000 })
      await expect(logs.events.first()).toContainText('Banned 203.0.113.9')

      // How they are spread is asked for again now and then, and when asked to.
      await logs.refresh.click()
      await expect(logs.matched).toHaveText('5 events')
    })

    test('stop when paused, and catch up when turned back on', async ({ harness, logs, page }) => {
      await harness.createEvents(SOME)
      await logs.goto()
      await expect(logs.events).toHaveCount(4)

      await logs.live.click()
      await page.evaluate(() => {
        window.scrollTo(0, 0)
      })

      await expect(logs.live).toHaveAttribute('aria-pressed', 'false')
      await expect(logs.updated).toContainText('Paused at')
      await harness.createEvents([{ summary: 'Banned 203.0.113.9', seconds_ago: 0 }])
      await logs.refresh.hover()
      await expect(logs.events).toHaveCount(4)

      await logs.live.click()
      // Clicking scrolled the button into view, and a page that is not at the top waits.
      await page.evaluate(() => {
        window.scrollTo(0, 0)
      })

      await expect(logs.live).toHaveAttribute('aria-pressed', 'true')
      await expect(logs.events).toHaveCount(5, { timeout: 15_000 })
    })

    test('hold what arrives while the page is scrolled down behind a button', async ({
      harness,
      logs,
      page,
    }) => {
      await harness.createEvents([{ summary: 'Blocked udp', repeat: 60, every_seconds: 20 }])
      await logs.goto()
      await expect(logs.events).toHaveCount(60)
      await page.evaluate(() => {
        window.scrollTo(0, document.body.scrollHeight)
      })

      await harness.createEvents([{ summary: 'Banned 203.0.113.9', seconds_ago: 0 }])

      await expect(logs.newEvents).toHaveText('1 new event', { timeout: 15_000 })
      await expect(logs.events).toHaveCount(60)

      await logs.newEvents.click()

      await expect(logs.newEvents).toBeHidden()
      await expect(logs.events).toHaveCount(61)
      await expect(logs.events.first()).toContainText('Banned 203.0.113.9')
      await expect.poll(() => page.evaluate(() => window.scrollY)).toBeLessThan(160)
    })
  })

  test.describe('can be downloaded', () => {
    test('as the file of whatever a search finds, in the format chosen', async ({
      harness,
      logs,
      page,
    }) => {
      await harness.createEvents(SOME)
      await logs.goto('?q=source%3Awazuh')
      await expect(logs.events).toHaveCount(1)

      await logs.export.click()
      await expect(logs.exportCsv).toHaveAttribute('href', /format=csv&q=source%3Awazuh/)
      const csv = await page.request.get((await logs.exportCsv.getAttribute('href')) ?? '')
      expect(csv.ok()).toBe(true)
      expect(csv.headers()['content-type']).toContain('text/csv')
      const lines = (await csv.text()).trim().split('\n')
      expect(lines).toHaveLength(2)
      expect(lines[1]).toContain(FAILED_LOGIN)

      await expect(logs.exportJson).toHaveAttribute('href', /format=json&q=source%3Awazuh/)
      const json = await page.request.get((await logs.exportJson.getAttribute('href')) ?? '')
      const events = (await json.json()) as Record<string, unknown>[]
      expect(events).toHaveLength(1)
      expect(events[0]).toMatchObject({ summary: FAILED_LOGIN, source: 'wazuh' })
      expect(events[0]?.raw).toMatchObject({ rule: { id: '5710' } })
    })
  })

  test.describe('when they cannot be loaded', () => {
    test('keep what they have, and say so, when asking again fails', async ({
      harness,
      logs,
      page,
    }) => {
      await harness.createEvents(SOME)
      await logs.goto()
      await expect(logs.events).toHaveCount(4)
      await page.route('**/api/logs?**', (route) => route.abort())

      await logs.refresh.click()

      await expect(logs.stale).toContainText('What is shown is from')
      await expect(logs.events).toHaveCount(4)
    })

    test('say so when they cannot be loaded at all, and load once they can', async ({
      harness,
      logs,
      page,
    }) => {
      await harness.createEvents(SOME)
      await page.route('**/api/logs?**', (route) => route.abort())

      await logs.goto()

      await expect(logs.error).toBeVisible()
      await page.unroute('**/api/logs?**')
      await logs.retry.click()
      await expect(logs.events).toHaveCount(4)
    })

    test('say so in the sheet when one event cannot be read, and try again on request', async ({
      harness,
      logs,
      page,
    }) => {
      await harness.createEvents(SOME)
      await logs.goto()
      await expect(logs.events).toHaveCount(4)
      await page.route(/\/api\/logs\/\d+\.\d+$/, (route) => route.abort())

      await logs.open(FAILED_LOGIN).click()

      await expect(logs.drawerError).toBeVisible()
      // What the list had is still shown.
      await expect(logs.drawerTitle).toHaveText(FAILED_LOGIN)
      await expect(logs.field('from')).toContainText(SCANNER)
      await page.unroute(/\/api\/logs\/\d+\.\d+$/)
      await logs.drawerError.getByTestId('drawer-retry').click()
      await expect(logs.rawText).toContainText('firedtimes')
      await expect(logs.drawerError).toBeHidden()
    })
  })
})
