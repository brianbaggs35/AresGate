import { expect, test, type Harness, type IntegrationPage } from '../support'

const TOKEN = 'a-valid-ntopng-token'
const KEY = 'a-valid-key'
const SECRET = 'a-valid-secret'

test.describe('integrations', () => {
  test('lists a card for each, which opens its own page', async ({
    page,
    shell,
    integrations,
    integration,
  }) => {
    await page.goto('/')

    await shell.integrationsLink.click()

    await expect(page).toHaveURL('/integrations')
    await expect(page).toHaveTitle('Integrations · AresGate')
    await expect(integrations.heading).toBeVisible()
    await expect(integrations.names).toHaveText(['OPNsense', 'ntopng', 'Wazuh', 'CrowdSec'])
    await expect(integrations.count).toHaveText('0 of 4 set up')
    for (const key of ['opnsense', 'ntopng', 'wazuh', 'crowdsec']) {
      await expect(integrations.status(key)).toHaveText('Not connected')
      await expect(integrations.lastCall(key)).toHaveText('Not set up yet')
    }
    await expect(shell.integrationsLink).toHaveAttribute('aria-current', 'page')

    await integrations.card('ntopng').click()

    await expect(page).toHaveURL('/integrations/ntopng')
    await expect(integration.title).toHaveText('ntopng')
    await expect(integration.status).toHaveText('Not connected')
    // The place in the menu stays marked on the integration's own page.
    await expect(shell.integrationsLink).toHaveAttribute('aria-current', 'page')

    await integration.back.click()

    await expect(page).toHaveURL('/integrations')
    await expect(integrations.names).toHaveCount(4)
  })

  test('explains how to get what is needed, and links to the official documentation', async ({
    integration,
  }) => {
    await integration.goto('ntopng')

    await expect(integration.guide).toContainText(/authentication token/i)
    await expect(integration.docs).toHaveAttribute('href', /^https:\/\/www\.ntop\.org\//)
    await expect(integration.docs).toHaveAttribute('target', '_blank')
    await expect(integration.docs).toHaveAttribute('rel', 'noopener noreferrer')
    await integration.guideToggle.click()
    await expect(integration.guide.getByRole('list')).toBeHidden()
  })

  test('says so when the list can’t be loaded, and loads it again on request', async ({
    page,
    integrations,
  }) => {
    let fail = true
    await page.route('**/api/integrations', (route) => (fail ? route.abort() : route.continue()))
    await integrations.goto()

    await expect(integrations.loadError).toContainText("Can't reach AresGate.")
    await expect(integrations.names).toHaveCount(0)

    fail = false
    await integrations.retry.click()

    await expect(integrations.loadError).toHaveCount(0)
    await expect(integrations.names).toHaveCount(4)
  })

  test('says so for an integration that does not exist', async ({ page, integration }) => {
    await integration.goto('nothing')

    await expect(integration.title).toHaveText('There is no such integration')
    await expect(integration.loadError).toContainText('no such integration')
    await expect(integration.retry).toHaveCount(0)
    await integration.back.click()
    await expect(page).toHaveURL('/integrations')
  })

  test.describe('ntopng', () => {
    test('connects, tests, and logs the request it made', async ({
      page,
      harness,
      integration,
      integrations,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      const answers: string[] = []
      page.on('response', (response) => {
        if (response.url().includes('/api/integrations')) {
          void response.text().then((text) => answers.push(text))
        }
      })
      await integration.goto('ntopng')
      await expect(integration.logEmpty).toContainText("hasn't made a request")

      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()

      await expect(integration.report).toContainText('The test passed')
      await expect(integration.report).toContainText('ntopng answered. Interface 0 is eth0.')
      await expect(integration.status).toHaveText('Connected')
      await expect(integration.save).toHaveText('Save and test')
      await expect(integration.connectionStatus('api')).toHaveText('Connected')
      await expect(integration.lastSuccess).toContainText('Last successful call')
      // The log has the request, with its path and no query string, and how it went.
      await expect(integration.logCalls).toHaveCount(1)
      await expect(integration.logCalls.first()).toContainText(
        '/lua/rest/v2/get/ntopng/interfaces.lua',
      )
      await expect(integration.logCalls.first()).toContainText('200')
      await expect(integration.logCalls.first().getByRole('img')).toHaveAttribute(
        'aria-label',
        'Worked',
      )
      // The token was sent once and never comes back.
      await expect(integration.field('api', 'token')).toHaveValue('')
      await expect(integration.field('api', 'token')).toHaveAttribute('placeholder', 'Saved')
      expect(answers.length).toBeGreaterThan(0)
      expect(answers.join('\n')).not.toContain(TOKEN)

      // It is still connected on the next visit, and the list shows it.
      await page.reload()
      await expect(integration.status).toHaveText('Connected')
      await expect(integration.address('api')).toHaveValue(ntopng.url)
      await integration.back.click()
      await expect(integrations.status('ntopng')).toHaveText('Connected')
      await expect(integrations.lastCall('ntopng')).toContainText('Last successful call')
      await expect(integrations.count).toHaveText('1 of 4 set up')
    })

    test('says so when the token is refused, and logs the failed request', async ({
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')

      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill('the wrong token')
      await integration.save.click()

      await expect(integration.report).toContainText('The test failed')
      await expect(integration.report).toContainText('ntopng redirected to its login page')
      await expect(integration.status).toHaveText('Problem')
      await expect(integration.lastError('api')).toContainText('The last test failed')
      // The log keeps it, and can show only what failed.
      await expect(integration.logCalls).toHaveCount(1)
      await expect(integration.logCalls.first().getByRole('img')).toHaveAttribute(
        'aria-label',
        'Failed',
      )
      await expect(integration.logCalls.first()).toContainText("which AresGate doesn't follow")
      await integration.chooseFilter('result', 'Worked')
      await expect(integration.logEmpty).toContainText('No requests match these filters')
      await integration.logClear.click()
      await expect(integration.logCalls).toHaveCount(1)
      await integration.chooseFilter('result', 'Failed')
      await expect(integration.logCalls).toHaveCount(1)
    })

    test('shows how the collectors reading from it are doing', async ({ harness, integration }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      // There is nothing to collect from until it is connected.
      await expect(integration.collection).toHaveCount(0)

      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')

      await expect(integration.collection).toBeVisible()
      await expect(integration.collectionWorker).toContainText("hasn't reported in yet")
      await expect(integration.collectionEmpty).toContainText('Nothing is being collected')

      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()

      await expect(integration.collectionWorker).toHaveCount(0)
      await expect(integration.collectors).toHaveCount(1)
      await expect(integration.collectors).toContainText('Connection check')
      await expect(integration.collectorStates).toHaveText('Working')
      await expect(integration.collectorTimings).toContainText('Last ran just now')
      await expect(integration.collectorTimings).toContainText('next run in 5 minutes')
      await expect(integration.collectorErrors).toHaveCount(0)
      // The collector's check is in the log with the ones made from this page.
      await integration.logRefresh.click()
      await expect(integration.logCalls).toHaveCount(2)
    })

    test('says why a collector failed, and that the worker has stopped', async ({
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill('the wrong token')
      await integration.save.click()
      await expect(integration.status).toHaveText('Problem')
      await harness.setWorker('stopped')
      await harness.runCollectors()

      await integration.collectionRefresh.click()

      await expect(integration.collectionWorker).toContainText('has stopped reporting in')
      await expect(integration.collectorStates).toHaveText('Problem')
      await expect(integration.collectorErrors).toContainText('ntopng redirected to its login page')
    })

    test('says so when the collectors can’t be loaded, and shows them again on request', async ({
      page,
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')
      await harness.setWorker('running')
      await harness.runCollectors()
      let fail = true
      await page.route('**/api/collectors**', (route) => (fail ? route.abort() : route.continue()))

      await integration.collectionRefresh.click()
      await expect(integration.collectionError).toContainText("Can't reach AresGate.")
      await expect(integration.collectors).toHaveCount(0)

      fail = false
      await integration.collectionRetry.click()

      await expect(integration.collectionError).toHaveCount(0)
      await expect(integration.collectors).toHaveCount(1)
    })

    test('fixing the token and saving again makes it work', async ({ harness, integration }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill('the wrong token')
      await integration.save.click()
      await expect(integration.status).toHaveText('Problem')

      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()

      await expect(integration.report).toContainText('The test passed')
      await expect(integration.status).toHaveText('Connected')
      await expect(integration.lastError('api')).toHaveCount(0)
      await expect(integration.logCalls).toHaveCount(2)
    })

    test('reaches an address it is not allowed to, and says why in the field', async ({
      integration,
    }) => {
      await integration.goto('ntopng')

      await integration.address('api').fill('http://8.8.8.8:3000')
      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()

      await expect(integration.problems).toBeVisible()
      await expect(integration.addressMessages('api')).toContainText('private network')
      await expect(integration.address('api')).toBeFocused()
      await expect(integration.status).toHaveText('Not connected')

      await integration.address('api').fill('http://169.254.169.254')
      await integration.save.click()
      await expect(integration.addressMessages('api')).toContainText('metadata services')
    })

    test('asks for what is missing, field by field', async ({ integration }) => {
      await integration.goto('ntopng')

      await integration.save.click()

      await expect(integration.problems).toBeVisible()
      await expect(integration.addressMessages('api')).not.toBeEmpty()
      await expect(integration.address('api')).toBeFocused()
      await expect(integration.fieldMessages('api', 'field-token')).toContainText('Enter')
    })

    test('keeps the saved token when only the address changes', async ({
      harness,
      integration,
    }) => {
      const first = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      const second = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      await integration.address('api').fill(first.url)
      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')
      await expect(integration.test).toBeEnabled()

      await integration.address('api').fill(second.url)

      // What is saved is tested, so changes have to be saved first.
      await expect(integration.test).toBeDisabled()
      await expect(integration.unsaved).toBeVisible()
      await integration.save.click()
      await expect(integration.report).toContainText('The test passed')
      await expect(integration.unsaved).toHaveCount(0)
      await expect(integration.test).toBeEnabled()
      await integration.test.click()
      await expect(integration.report).toContainText('The test passed')
    })

    test('switches to a user name and password, which asks for those instead', async ({
      integration,
    }) => {
      await integration.goto('ntopng')
      await expect(integration.field('api', 'token')).toBeVisible()

      await integration.connection('api').getByLabel('Username and password').check()

      await expect(integration.field('api', 'token')).toHaveCount(0)
      await expect(integration.field('api', 'username')).toBeVisible()
      await expect(integration.field('api', 'password')).toBeVisible()
    })

    test('forgets the connection when it is disconnected, after asking', async ({
      page,
      harness,
      integration,
      integrations,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')

      await integration.disconnect.click()
      await expect(integration.confirmation).toBeVisible()
      await expect(integration.confirmation).toContainText('Disconnect ntopng?')
      await expect(page.getByRole('dialog', { name: 'Disconnect ntopng?' })).toBeVisible()
      await integration.cancelDisconnect.click()
      await expect(integration.confirmation).toBeHidden()
      await expect(integration.disconnect).toBeFocused()
      await expect(integration.status).toHaveText('Connected')

      await integration.disconnect.click()
      await integration.confirmDisconnect.click()

      await expect(integration.confirmation).toBeHidden()
      await expect(integration.notice).toContainText('ntopng is disconnected')
      await expect(integration.status).toHaveText('Not connected')
      await expect(integration.address('api')).toHaveValue('')
      await expect(integration.field('api', 'token')).not.toHaveAttribute('placeholder', 'Saved')
      await expect(integration.save).toHaveText('Connect')
      await expect(integration.disconnect).toHaveCount(0)
      await expect(integration.test).toHaveCount(0)
      // What it logged stays in the log.
      await expect(integration.logCalls).toHaveCount(1)
      await integration.back.click()
      await expect(integrations.status('ntopng')).toHaveText('Not connected')
    })
  })

  test.describe('when AresGate can’t be reached', () => {
    test('says so for testing, saving and disconnecting, and changes nothing', async ({
      page,
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')
      let fail = true
      await page.route(/\/api\/integrations\/ntopng(\/test)?$/, (route) =>
        fail && route.request().method() !== 'GET' ? route.abort() : route.continue(),
      )

      await integration.test.click()
      await expect(integration.failure).toContainText("Can't reach AresGate.")
      await expect(integration.status).toHaveText('Connected')

      await integration.disconnect.click()
      await integration.confirmDisconnect.click()
      // The dialog closes either way, so what happened shows on the page behind it.
      await expect(integration.confirmation).toBeHidden()
      await expect(integration.failure).toContainText("Can't reach AresGate.")
      await expect(integration.status).toHaveText('Connected')
      await expect(integration.address('api')).toHaveValue(ntopng.url)

      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()
      await expect(integration.failure).toContainText("Can't reach AresGate.")

      fail = false
      await integration.save.click()
      await expect(integration.report).toContainText('The test passed')
      await expect(integration.failure).toHaveCount(0)
    })

    test('says so when the log can’t be loaded, and shows it again on request', async ({
      page,
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()
      await expect(integration.logCalls).toHaveCount(1)
      let fail = true
      await page.route('**/api/integrations/ntopng/calls*', (route) =>
        fail ? route.abort() : route.continue(),
      )

      await integration.logRefresh.click()
      await expect(integration.logError).toContainText("Can't reach AresGate.")
      await expect(integration.logCalls).toHaveCount(0)

      fail = false
      await integration.logRefresh.click()
      await expect(integration.logError).toHaveCount(0)
      await expect(integration.logCalls).toHaveCount(1)
    })
  })

  test.describe('CrowdSec', () => {
    test('warns about plain http, and connects with an API key', async ({
      harness,
      integration,
    }) => {
      const crowdsec = await harness.standIn({ kind: 'crowdsec', api_key: KEY })
      await integration.goto('crowdsec')
      await expect(integration.plainHttpWarning('lapi')).toHaveCount(0)

      await integration.address('lapi').fill(crowdsec.url)

      await expect(integration.plainHttpWarning('lapi')).toContainText('without encryption')
      // There is no certificate to decide about on a plain http address.
      await expect(integration.connection('lapi').getByTestId('lapi-tls')).toHaveCount(0)
      await integration.field('lapi', 'api_key').fill(KEY)
      await integration.save.click()
      await expect(integration.report).toContainText('accepted the key')
      await expect(integration.status).toHaveText('Connected')
    })

    test('says so when the API key is not accepted', async ({ harness, integration }) => {
      const crowdsec = await harness.standIn({ kind: 'crowdsec', api_key: KEY })
      await integration.goto('crowdsec')
      await integration.address('lapi').fill(crowdsec.url)
      await integration.field('lapi', 'api_key').fill('not the key')

      await integration.save.click()

      await expect(integration.report).toContainText("didn't accept the credentials")
      await expect(integration.status).toHaveText('Problem')
      await integration.chooseFilter('result', 'Failed')
      await expect(integration.logCalls).toHaveCount(1)
      await expect(integration.logCalls.first()).toContainText('403')
    })
  })

  /** Connects OPNsense to a stand-in with these services installed, pinning its certificate. */
  async function connectFirewall(
    harness: Harness,
    integration: IntegrationPage,
    services: string[],
  ): Promise<void> {
    const firewall = await harness.standIn({
      kind: 'opnsense',
      api_key: KEY,
      api_secret: SECRET,
      services,
    })
    await integration.goto('opnsense')
    await integration.address('api').fill(firewall.url)
    await integration.field('api', 'api_key').fill(KEY)
    await integration.field('api', 'api_secret').fill(SECRET)
    await integration.tlsMode('api', 'pinned').check()
    await integration.lookUp('api').click()
    await integration.trust('api').click()
    await integration.save.click()
    await expect(integration.status).toHaveText('Connected')
  }

  test.describe('OPNsense', () => {
    test('pins its own certificate, finds the services that run on it and reads from them', async ({
      page,
      harness,
      integration,
      integrations,
    }) => {
      const firewall = await harness.standIn({
        kind: 'opnsense',
        api_key: KEY,
        api_secret: SECRET,
        services: ['suricata', 'openvpn'],
      })
      await integration.goto('opnsense')
      await expect(integration.connection('api')).toBeVisible()
      await integration.address('api').fill(firewall.url)
      await integration.field('api', 'api_key').fill(KEY)
      await integration.field('api', 'api_secret').fill(SECRET)

      // Its certificate is its own, which the computer doesn't trust.
      await integration.save.click()
      await expect(integration.report).toContainText('The test failed')
      await expect(integration.status).toHaveText('Problem')

      // So it is looked up, compared and pinned.
      await integration.tlsMode('api', 'pinned').check()
      await expect(integration.lookUp('api')).toBeEnabled()
      await integration.lookUp('api').click()
      await expect(integration.found('api')).toContainText('CN=fw.home.arpa')
      await expect(integration.foundFingerprint('api')).toHaveText(firewall.fingerprint ?? '')
      await integration.trust('api').click()
      await expect(integration.fingerprint('api')).toHaveValue(firewall.fingerprint ?? '')
      await expect(integration.trusted('api')).toBeVisible()

      await integration.save.click()

      await expect(integration.report).toContainText('The test passed')
      await expect(integration.report).toContainText('OPNsense answered: OPNsense 25.7.1-amd64.')
      await expect(integration.report).toContainText(
        'Services found: Suricata (running), OpenVPN (running).',
      )
      await expect(integration.status).toHaveText('Connected')
      await expect(integration.module('api', 'Suricata')).toContainText('Running')
      await expect(integration.module('api', 'OpenVPN')).toContainText('Running')
      await expect(integration.module('api', 'CrowdSec')).toContainText('Not installed')
      await expect(integration.moduleSwitch('api', 'CrowdSec')).toBeDisabled()
      await expect(integration.moduleSwitch('api', 'Suricata')).toBeChecked()
      // Every request of the test is in the log, none with a secret or a query string.
      await expect(integration.logCalls.first()).toContainText('/api/')
      const text = await integration.log.innerText()
      expect(text).not.toContain(SECRET)
      expect(text).not.toContain(KEY)

      // One service can be left alone.
      await integration.moduleSwitch('api', 'OpenVPN').uncheck()
      await expect(integration.unsaved).toBeVisible()
      await integration.save.click()
      await expect(integration.report).toContainText('The test passed')
      await expect(integration.moduleSwitch('api', 'OpenVPN')).not.toBeChecked()

      // The list shows what was found.
      await page.goto('/integrations')
      await expect(integrations.status('opnsense')).toHaveText('Connected')
      await expect(integrations.services('opnsense')).toHaveText([
        'Firewall and system',
        'Suricata',
      ])
    })

    test('reads its firewall log and what it measures beside the connection check', async ({
      harness,
      integration,
    }) => {
      await connectFirewall(harness, integration, [])

      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()

      // Suricata isn't installed on this one, so it has no job for its alerts. The jobs are
      // listed by name.
      await expect(integration.collectors).toHaveCount(6)
      await expect(integration.collectors).toContainText([
        'Connection check',
        'Processor use',
        'Firewall log',
        'Gateways',
        'Interface traffic',
        'System health',
      ])
      await expect(integration.collectorStates).toHaveText(new Array(6).fill('Working'))
      await expect(integration.collectorTimings.nth(2)).toContainText('next run within a minute')
      await expect(integration.collectorErrors).toHaveCount(0)
      // The three lines in the firewall's log are kept once, however often they are read.
      expect((await harness.rowCounts()).events).toBe(3)
      // What it measures is read again each time: 14 numbers for two interfaces, 9 for its
      // health, 4 for its gateway and 1 for its processors.
      expect((await harness.rowCounts()).metric_samples).toBe(28)
      await harness.runCollectors()
      expect((await harness.rowCounts()).events).toBe(3)
      expect((await harness.rowCounts()).metric_samples).toBe(56)
    })

    test('reads the alerts of Suricata as well when it is installed', async ({
      harness,
      integration,
    }) => {
      await connectFirewall(harness, integration, ['suricata'])

      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()

      await expect(integration.collectors).toHaveCount(7)
      await expect(integration.collectors.nth(5)).toContainText('Suricata alerts')
      await expect(integration.collectorStates).toHaveText(new Array(7).fill('Working'))
      await expect(integration.collectorErrors).toHaveCount(0)
      // Three lines of the firewall's log and two alerts, kept once however often they are read.
      expect((await harness.rowCounts()).events).toBe(5)
      await harness.runCollectors()
      expect((await harness.rowCounts()).events).toBe(5)
    })

    test('a certificate lookup says why it could not be done', async ({ integration }) => {
      await integration.goto('opnsense')
      await integration.address('api').fill('https://203.0.113.5')
      await integration.tlsMode('api', 'pinned').check()

      await integration.lookUp('api').click()

      await expect(integration.lookUpError('api')).toContainText('private network')
      await expect(integration.found('api')).toHaveCount(0)
    })

    test('takes a certificate authority that is pasted', async ({ integration }) => {
      await integration.goto('opnsense')
      await integration.address('api').fill('https://192.168.1.1')
      await integration.field('api', 'api_key').fill(KEY)
      await integration.field('api', 'api_secret').fill(SECRET)
      await integration.tlsMode('api', 'ca').check()
      await integration.authority('api').fill('not a certificate')

      await integration.save.click()

      await expect(integration.connection('api').getByTestId('tls-ca-pem')).toContainText(
        'certificate',
      )
      await expect(integration.authority('api')).toBeFocused()
    })

    test('adds Zenarmor, which has its own address and key, only when it is wanted', async ({
      harness,
      integration,
    }) => {
      const services = ['suricata']
      const firewall = await harness.standIn({
        kind: 'opnsense',
        api_key: KEY,
        api_secret: SECRET,
        services,
      })
      const zenarmor = await harness.standIn({ kind: 'zenarmor', api_key: KEY })
      await integration.goto('opnsense')
      await expect(integration.address('zenarmor')).toHaveCount(0)
      await integration.address('api').fill(firewall.url)
      await integration.field('api', 'api_key').fill(KEY)
      await integration.field('api', 'api_secret').fill(SECRET)
      await integration.tlsMode('api', 'pinned').check()
      await integration.fingerprint('api').fill(firewall.fingerprint ?? '')

      await integration.useConnection('zenarmor').check()
      await integration.address('zenarmor').fill(zenarmor.url)
      await integration.field('zenarmor', 'user').fill('admin')
      await integration.field('zenarmor', 'api_key').fill(KEY)
      await integration.tlsMode('zenarmor', 'pinned').check()
      await integration.fingerprint('zenarmor').fill(zenarmor.fingerprint ?? '')
      await integration.save.click()

      await expect(integration.report).toContainText('The test passed')
      await expect(integration.checks).toHaveCount(2)
      await expect(integration.checks.nth(0)).toContainText('OPNsense API:')
      await expect(integration.checks.nth(1)).toContainText("Zenarmor's API accepted the key.")
      await expect(integration.connectionStatus('zenarmor')).toHaveText('Connected')
      // The log tells the two apart.
      await expect(integration.filter('connection')).toBeVisible()
      await integration.chooseFilter('connection', 'Zenarmor API')
      await expect(integration.logCalls).toHaveCount(1)
      await expect(integration.logCalls.first()).toContainText('/policies')
      await expect(integration.logCalls.first()).toContainText('Zenarmor API')

      // Switching it off and saving forgets it.
      await integration.useConnection('zenarmor').uncheck()
      await expect(integration.connection('zenarmor')).toContainText('forgets its address and key')
      await integration.save.click()
      await expect(integration.checks).toHaveCount(1)
      await expect(integration.useConnection('zenarmor')).not.toBeChecked()
      await expect(integration.address('zenarmor')).toHaveCount(0)
    })
  })

  test.describe('the log', () => {
    test('shows older requests on request and narrows by method and time', async ({
      harness,
      integration,
    }) => {
      const crowdsec = await harness.standIn({ kind: 'crowdsec', api_key: KEY })
      await integration.goto('crowdsec')
      await integration.address('lapi').fill(crowdsec.url)
      await integration.field('lapi', 'api_key').fill(KEY)
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')
      // Each test is a request; 26 of them are more than a page.
      for (let tested = 0; tested < 26; tested++) {
        await integration.test.click()
        await expect(integration.logCalls).toHaveCount(Math.min(tested + 2, 25))
      }
      await expect(integration.logOlder).toBeVisible()

      await integration.logOlder.click()

      await expect(integration.logCalls).toHaveCount(27)
      await expect(integration.logOlder).toHaveCount(0)

      await integration.chooseFilter('method', 'POST')
      await expect(integration.logEmpty).toContainText('No requests match these filters')
      // Filtering starts again from the newest page.
      await integration.chooseFilter('method', 'GET')
      await expect(integration.logCalls).toHaveCount(25)
      await expect(integration.logOlder).toBeVisible()
      await integration.chooseFilter('period', 'Last hour')
      await expect(integration.logCalls).toHaveCount(25)
      await integration.logRefresh.click()
      await expect(integration.logCalls).toHaveCount(25)
    })
  })
})
