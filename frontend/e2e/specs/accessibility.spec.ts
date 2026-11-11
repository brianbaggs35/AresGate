import {
  authenticatorCode,
  connectFirewall,
  expect,
  expectAccessible,
  test,
  turnOnAi,
} from '../support'

// Both themes, since contrast is checked against the colors each one draws.
for (const theme of ['light', 'dark'] as const) {
  test.describe(`accessibility in the ${theme} theme`, () => {
    test('the dashboard has no WCAG 2.2 AA problems', async ({ page, dashboard, shell }) => {
      await dashboard.goto()
      await expect(dashboard.banner).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the assets have no WCAG 2.2 AA problems', async ({ page, harness, assets, shell }) => {
      await harness.createAssets({
        devices: [
          {
            hostname: 'laptop',
            mac: '00:11:22:0a:0b:0c',
            vendor: 'Example Devices Inc.',
            addresses: ['192.168.1.20', '192.168.1.21', '192.168.1.22', '192.168.1.23'],
            listed: [
              { source: 'opnsense', via: 'arp', minutes_ago: 1 },
              { source: 'ntopng', via: 'hosts', minutes_ago: 1 },
            ],
          },
          {
            hostname: 'phone',
            mac: '02:aa:bb:cc:dd:ee',
            addresses: ['192.168.1.9'],
            listed: [{ source: 'opnsense', via: 'dhcp', minutes_ago: 30 }],
            first_seen_hours: 30,
          },
          {
            hostname: 'camera',
            addresses: ['192.168.20.40'],
            listed: [{ source: 'opnsense', via: 'arp', minutes_ago: 3 * 24 * 60 }],
            first_seen_hours: 24 * 50,
          },
          { mac: '00:11:22:0a:0b:0e' },
        ],
        hosts: [{ key: '002', hostname: 'laptop', address: '192.168.1.20' }, { key: '003' }],
      })
      await assets.goto()
      await expect(assets.cards).toHaveCount(5)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      // A state chosen, the choices that narrow the list on, and a search with nothing in it.
      await assets.view('online').click()
      await assets.newOnly.click()
      await expectAccessible(page)
      await assets.find('no such device')
      await expect(assets.emptyTitle).toHaveText('Nothing matches')
      await expectAccessible(page)
    })

    test('the assets of a network with nothing connected have no WCAG 2.2 AA problems', async ({
      page,
      assets,
      shell,
    }) => {
      await assets.goto()
      await expect(assets.emptyTitle).toHaveText('No devices yet')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('an asset, with its traffic and its events, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      assets,
      asset,
      shell,
    }) => {
      await harness.createAssets({
        devices: [
          {
            hostname: 'laptop',
            mac: '00:11:22:0a:0b:0c',
            vendor: 'Example Devices Inc.',
            addresses: ['192.168.1.20'],
            earlier: ['192.168.1.19'],
            listed: [
              { source: 'opnsense', via: 'arp', minutes_ago: 1 },
              { source: 'ntopng', via: 'hosts', minutes_ago: 1 },
            ],
          },
        ],
      })
      await harness.createTraffic([
        { host: '192.168.1.20', sent: [1000, 3000, 6000, 10000], received: [500, 600, 700, 900] },
      ])
      await harness.createEvents([
        {
          source: 'opnsense',
          kind: 'firewall',
          severity: 'info',
          summary: 'Blocked tcp from 192.168.1.20 to 52.1.2.3',
          src_address: '192.168.1.20',
          dst_address: '52.1.2.3',
          dst_port: 443,
          protocol: 'tcp',
          seconds_ago: 60,
        },
      ])
      await assets.goto()
      await assets.open('laptop')
      await expect(asset.heading).toHaveText('laptop')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the incidents, and the page of one, have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      incidents,
      incident,
      shell,
    }) => {
      await harness.createIncidents([
        {
          address: '93.184.216.34',
          severity: 'critical',
          programs: ['wazuh', 'opnsense', 'crowdsec'],
          signals: 8,
          ban: true,
          blocks: 2,
          blocks_after_ban: 3,
          dropped: 1,
          minutes_ago: 4,
          device_name: 'nas',
        },
        { address: '8.8.8.8', severity: 'high', programs: ['wazuh', 'opnsense'], signals: 3 },
        { address: '1.1.1.1', severity: 'medium', programs: ['ntopng'], status: 'investigating' },
        { address: '9.9.9.9', severity: 'low', programs: ['opnsense'], status: 'resolved' },
      ])
      await incidents.goto()
      await expect(incidents.cards).toHaveCount(3)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      // Some of them picked, with the row that changes them, and a change looked over.
      await incidents.picks.nth(0).click()
      await incidents.picks.nth(1).click()
      await expect(incidents.picked).toHaveText('2 selected')
      // Clicking the second one scrolled the list, which can leave the next card's box half under the
      // bar at the bottom of a phone: a box that is only partly on the screen is not what is checked.
      await page.evaluate(() => {
        window.scrollTo(0, 0)
      })
      await expectAccessible(page)
      await incidents.bulkVerdict('not_suspicious').click()
      await expect(incidents.dialogLines.first()).toBeVisible()
      await expectAccessible(page)
      await incidents.dialogCancel.click()
      await incidents.letGo.click()

      // A search, the terms it was understood as, and what the results are made of.
      await incidents.search('severity>=high -address:8.8.8.8')
      await expect(incidents.terms).toHaveCount(2)
      await expect(incidents.facets).toBeVisible()
      await expectAccessible(page)

      // The ways to search, and the searches made before.
      await incidents.searchHelp.click()
      await expect(incidents.searchPanel).toBeVisible()
      await expect(incidents.recent).toHaveCount(1)
      await expectAccessible(page)

      // A search kept under a name, and the one just kept in the list.
      await incidents.saved.keep('Serious ones')
      await expect(incidents.saved.notice).toHaveText('Saved as Serious ones.')
      await expect(incidents.saved.rows).toHaveCount(1)
      await expectAccessible(page)
      await incidents.searchHelp.click()

      // A search that can not be understood.
      await incidents.search('sevrity:high')
      await expect(incidents.searchField).toContainText('Did you mean')
      await expectAccessible(page)

      await incidents.goto('?view=all&q=address%3A203.0.113.77')
      await expect(incidents.empty).toContainText('Nothing matches')
      await expectAccessible(page)

      await incidents.goto()
      await incidents.cards.first().click()
      await expect(incident.reasonsCard).toBeVisible()
      await expect(incident.signals.first()).toBeVisible()
      await expectAccessible(page)

      await incident.action('investigating').click()
      await expect(incident.notice).toBeVisible()
      await expectAccessible(page)
    })

    test('what the AI makes of an incident has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      aiSettings,
      incidents,
      incident,
      shell,
    }) => {
      await harness.createIncidents([
        {
          address: '93.184.216.34',
          severity: 'high',
          programs: ['wazuh', 'opnsense'],
          signals: 4,
          device_name: 'nas',
        },
      ])
      await turnOnAi(harness, aiSettings)
      await incidents.goto()
      await incidents.cards.first().click()
      await expect(incident.aiUnread).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await incident.aiAsk.click()
      await expect(incident.aiClass).toBeVisible()
      await expect(incident.aiSuggestion).toBeVisible()
      await expectAccessible(page)

      await incidents.goto()
      await expect(page.getByTestId('call-chip')).toBeVisible()
      await expectAccessible(page)
    })

    test('the verdicts, on an incident and in the settings, have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      incidents,
      incident,
      verdicts,
      shell,
    }) => {
      await harness.createIncidents([
        { address: '93.184.216.34', severity: 'high', programs: ['wazuh', 'opnsense'], signals: 4 },
        { address: '8.8.8.8', programs: ['wazuh'], signals: 2 },
      ])
      await harness.createVerdicts([
        { verdict: 'not_suspicious', address: '8.8.8.8', note: 'my scanner' },
        { verdict: 'low_priority', source: 'wazuh', signature: 'ET SCAN Potential SSH Scan' },
      ])
      await incidents.goto('?quieted=1')
      await expect(incidents.cards).toHaveCount(2)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      // The list with the incidents your verdicts quiet, and its switch.
      await expect(incidents.quieted).toBeVisible()
      await expectAccessible(page)

      // An incident with signals that don't count, and the verdict that says so.
      await incidents.goto('?quieted=1&address=93.184.216.34')
      await incidents.cards.first().click()
      await expect(incident.applied).toHaveCount(1)
      await expect(incident.signals.first()).toBeVisible()
      await expectAccessible(page)

      await incident.give('threat').click()
      await expect(incident.verdictNotice).toBeVisible()
      await expectAccessible(page)

      // An incident that is quieted as a whole, by two verdicts: the milder says so.
      await incidents.goto('?quieted=1&address=8.8.8.8')
      await incidents.cards.first().click()
      await expect(incident.verdictChip).toHaveText('Low priority')
      await expectAccessible(page)

      await verdicts.goto()
      await expect(verdicts.rows).toHaveCount(3)
      await expectAccessible(page)

      await verdicts.rows.first().getByTestId('verdict-change').click()
      await expect(verdicts.dialog).toBeVisible()
      await expectAccessible(page)
      await verdicts.cancel.click()
      await expect(verdicts.dialog).toBeHidden()

      await verdicts.rows.first().getByTestId('verdict-remove').click()
      await expect(verdicts.confirmTitle).toBeVisible()
      await expectAccessible(page)
    })

    test('the noise filters, and an incident with signals set aside, have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      noiseFilters,
      incidents,
      incident,
      shell,
    }) => {
      await harness.createIncidents([
        { address: '93.184.216.34', severity: 'high', programs: ['wazuh'], signals: 2 },
        { address: '8.8.8.8', severity: 'low', programs: ['wazuh'], signals: 1 },
        { address: '192.168.1.77', severity: 'high', programs: ['wazuh'], signals: 2 },
      ])
      await noiseFilters.goto()
      await expect(noiseFilters.sources).toHaveCount(1)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      // Everything changed at once, with what it would do worked out.
      await noiseFilters.floorSlider.focus()
      await page.keyboard.press('ArrowRight')
      await noiseFilters.chooseFloor('Wazuh', 'High and up')
      await noiseFilters.insideSwitch.check()
      await noiseFilters.chooseGap('scan', '8 hours')
      await noiseFilters.chooseMinimum('2 low alerts')
      await expect(noiseFilters.effectTable).toBeVisible()
      await expect(noiseFilters.figure('set-aside').after).toHaveText('4')
      await expectAccessible(page)

      await noiseFilters.save.click()
      await expect(noiseFilters.saved).toBeVisible()
      await expectAccessible(page)

      // An incident whose signals were set aside, with the chip that says by which filter.
      await incidents.goto('?address=8.8.8.8')
      await incidents.cards.first().click()
      await expect(incident.signals.getByTestId('signal-filtered')).toHaveCount(1)
      await expectAccessible(page)
    })

    test('the threats, the kinds of incident and one kind have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      threats,
      kinds,
      kind,
      incidents,
      shell,
    }) => {
      await harness.createIncidents([
        {
          address: '93.184.216.34',
          severity: 'critical',
          programs: ['wazuh', 'opnsense'],
          signals: 3,
          exploit: true,
          compromise: true,
          minutes_ago: 8,
          device_name: 'nas',
        },
        { address: '1.1.1.1', severity: 'high', programs: ['wazuh'], signals: 2, minutes_ago: 20 },
        {
          address: '8.8.4.10',
          severity: 'low',
          programs: ['opnsense'],
          twin: 'ntopng',
          signals: 4,
          scan: true,
          neighbours: 2,
          waves: 2,
          minutes_ago: 30,
        },
      ])
      await threats.goto()
      await expect(threats.cards).toHaveCount(1)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await threats.lane('suspect').click()
      await expect(threats.cards).toHaveCount(1)
      await expectAccessible(page)

      await threats.lane('background').click()
      await expect(threats.kinds.first()).toBeVisible()
      await expectAccessible(page)

      await kinds.goto()
      await expect(kinds.cards).toHaveCount(2)
      await expectAccessible(page)

      await kinds.cards.first().getByTestId('family').click()
      await expect(kind.judgementNone).toBeVisible()
      await kind.watch.click()
      await expect(kind.judgementOwner).toBeVisible()
      await expectAccessible(page)

      // The incident that says why it is where it is and what kept happening.
      await incidents.goto('?address=8.8.4.10')
      await incidents.cards.first().click()
      await expect(page.getByTestId('where-card')).toBeVisible()
      await expect(page.getByTestId('occurrences-card')).toBeVisible()
      await expectAccessible(page)
    })

    test('what the programs said of an incident has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      incidents,
      shell,
    }) => {
      await harness.createIncidents([
        {
          address: '8.8.4.11',
          severity: 'high',
          programs: ['wazuh', 'ntopng'],
          signals: 4,
          twin: 'opnsense',
          detailed: true,
          minutes_ago: 5,
        },
      ])

      await incidents.goto('?address=8.8.4.11')
      await incidents.cards.first().click()
      await expect(page.getByTestId('insights-card')).toBeVisible()
      await expect(page.getByTestId('evidence-excerpt').first()).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)
    })

    test('the threat detection settings have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      threatSettings,
      shell,
    }) => {
      await harness.createIncidents([
        { address: '1.1.1.1', severity: 'high', programs: ['wazuh'], signals: 2 },
      ])
      await threatSettings.goto()
      await expect(threatSettings.levelValue).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      // Everything changed at once, with what it would do worked out.
      await threatSettings.levelSlider.focus()
      for (let step = 0; step < 5; step++) await page.keyboard.press('ArrowLeft')
      await threatSettings.exposure('some').check()
      await threatSettings.ports.fill('22, https')
      await threatSettings.notes.fill('A web server.')
      await expect(threatSettings.effectTable).toBeVisible()
      await expectAccessible(page)

      await threatSettings.ports.fill('22, 443')
      await threatSettings.save.click()
      await expect(threatSettings.saved).toBeVisible()
      await expectAccessible(page)
    })

    test('the logs, a search of them and the sheet for an event have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      logs,
      shell,
    }) => {
      await harness.createEvents([
        {
          source: 'opnsense',
          summary: 'Blocked tcp from 203.0.113.7',
          src_address: '203.0.113.7',
          src_port: 51234,
          dst_address: '192.168.1.20',
          dst_port: 443,
          protocol: 'tcp',
          seconds_ago: 60,
          raw: { action: 'block', interface: 'wan', reason: 'match' },
        },
        {
          source: 'wazuh',
          kind: 'alert',
          severity: 'critical',
          summary: 'sshd: Failed password for root',
          signature: '5710 sshd: Attempt to login using a non-existent user',
          src_address: '203.0.113.7',
          dst_address: '192.168.1.20',
          dst_port: 22,
          seconds_ago: 120,
          raw: { rule: { id: '5710', level: 10 }, full_log: 'Failed password for root' },
        },
        {
          source: 'opnsense',
          kind: 'alert',
          severity: 'high',
          summary: 'ET SCAN',
          seconds_ago: 180,
        },
        {
          source: 'ntopng',
          kind: 'flow',
          severity: 'low',
          summary: 'Long flow',
          seconds_ago: 7200,
        },
        {
          source: 'crowdsec',
          kind: 'decision',
          severity: 'medium',
          summary: 'Banned',
          seconds_ago: 9000,
        },
      ])
      await logs.goto()
      await expect(logs.events).toHaveCount(5)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expect(logs.volume).toBeVisible()
      await expectAccessible(page)

      // A search, the terms it was understood as, and what the results are made of.
      await logs.search('severity>=low -port:443')
      await expect(logs.terms).toHaveCount(2)
      await expect(logs.facets).toBeVisible()
      await expectAccessible(page)

      // The ways to search, and the searches made before.
      await logs.searchHelp.click()
      await expect(logs.searchPanel).toBeVisible()
      await expect(logs.recent).toHaveCount(1)
      await expectAccessible(page)

      // A search kept under a name, and the one just kept in the list.
      await logs.saved.keep('Not the web')
      await expect(logs.saved.notice).toHaveText('Saved as Not the web.')
      await expect(logs.saved.rows).toHaveCount(1)
      await expectAccessible(page)
      await logs.searchHelp.click()

      // A search that can not be understood, and one that finds nothing.
      await logs.search('sevrity:high')
      await expect(logs.searchField).toContainText('Did you mean')
      await expectAccessible(page)
      await logs.search('198.51.100.99')
      await expect(logs.empty).toContainText('Nothing matches')
      await expectAccessible(page)

      // The files that can be downloaded, and the live switch turned off.
      await logs.goto()
      await expect(logs.events).toHaveCount(5)
      await logs.export.click()
      await expect(logs.exportCsv).toBeVisible()
      await expectAccessible(page)
      await page.keyboard.press('Escape')
      await logs.live.click()
      await expect(logs.live).toHaveAttribute('aria-pressed', 'false')
      await expectAccessible(page)

      // An event in its sheet, with its record, and one that has none.
      await logs.open('sshd: Failed password').click()
      await expect(logs.rawText).toBeVisible()
      await expect(logs.drawerNoIncident).toBeVisible()
      await expectAccessible(page)
      await logs.drawerOlder.click()
      await expect(logs.drawerTitle).toHaveText('ET SCAN')
      await expect(logs.rawNone).toBeVisible()
      await expectAccessible(page)
    })

    test('the AI page, with a provider working, one failing and a model list open, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      aiSettings,
      shell,
    }) => {
      await harness.standIn({
        kind: 'anthropic',
        api_key: 'sk-a-key-for-the-stand-in',
        models: ['claude-haiku-5-5'],
        provider: 'anthropic',
      })
      await harness.standIn({ kind: 'openai', api_key: 'another-key', provider: 'openai' })
      const ollama = await harness.standIn({ kind: 'ollama', models: ['qwen3:8b', 'llama3.2:3b'] })
      await harness.standIn({
        kind: 'ollama',
        api_key: 'a-cloud-key',
        models: ['gemma4:31b', 'glm-5.2'],
        paid: ['glm-5.2'],
        provider: 'ollama_cloud',
      })
      await aiSettings.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expect(aiSettings.choosePrompt).toBeVisible()
      await expectAccessible(page)

      await aiSettings.choose('anthropic')
      await aiSettings.apiKey('anthropic').fill('sk-a-key-for-the-stand-in')
      await aiSettings.test('anthropic').click()
      await expect(aiSettings.status('anthropic')).toHaveText('Connected')
      await aiSettings.enabled.check()
      await expectAccessible(page)

      await aiSettings.choose('openai')
      await aiSettings.apiKey('openai').fill('the-wrong-key')
      await aiSettings.test('openai').click()
      await expect(aiSettings.lastError('openai')).toBeVisible()
      await expectAccessible(page)

      await aiSettings.choose('ollama')
      await aiSettings.address('ollama').fill(ollama.url)
      await aiSettings.fetchModels('ollama').click()
      await expect(aiSettings.notice('ollama')).toHaveText('It has 2 models.')
      await expectAccessible(page)

      // The account to choose for Ollama's cloud, and what a free one is offered.
      await aiSettings.choose('ollama_cloud')
      await aiSettings.apiKey('ollama_cloud').fill('a-cloud-key')
      await aiSettings.fetchModels('ollama_cloud').click()
      await expect(aiSettings.notice('ollama_cloud')).toHaveText('It has 2 models.')
      await expect(aiSettings.freeModels('ollama_cloud')).toBeVisible()
      await expectAccessible(page)

      await aiSettings.openModels('ollama_cloud')
      await expect(aiSettings.modelOptions).toHaveText([/gemma4:31b/])
      await expectAccessible(page)
      await page.keyboard.press('Escape')

      await aiSettings.choose('anthropic')
      await aiSettings.openModels('anthropic')
      await expect(page.getByRole('option', { name: /Sonnet 5\.5/ })).toBeVisible()
      await expectAccessible(page)
      await page.keyboard.press('Escape')

      // A model that is being retired says so, beside its price and how it is cached.
      await aiSettings.choose('openai')
      await aiSettings.chooseModel('openai', /GPT-5\.4 nano/)
      await expect(aiSettings.price('openai')).toContainText('lists this model as deprecated')
      await expectAccessible(page)
    })

    test('the not-found page has no WCAG 2.2 AA problems', async ({ page, shell }) => {
      await page.goto('/no/such/page')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the AI usage page, with its charts, requests and a request opened, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      aiUsage,
      shell,
    }) => {
      await harness.createAiCalls([
        { about: 'incident 3', hours_ago: 2, cost_micros: 2_500, repeat: 3 },
        { about: 'incident 4', hours_ago: 30, cost_micros: 4_000, cached_tokens: 600 },
        { purpose: 'chat', model: 'a-model-nobody-priced', cost_micros: null, hours_ago: 7 },
        { about: 'incident 5', ok: false, error: "It didn't answer in time.", hours_ago: 50 },
      ])
      await aiUsage.goto()
      await expect(aiUsage.requests.first()).toBeVisible()
      await expect(aiUsage.dailyChart).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)

      await aiUsage.requests.first().getByTestId('call-open').click()
      await expect(aiUsage.dialog).toBeVisible()
      await expectAccessible(page)
    })

    test('the assistant, empty, with an answer and what it was based on, and a request opened, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      aiSettings,
      assistant,
      shell,
    }) => {
      await harness.createIncidents([
        {
          address: '93.184.216.34',
          severity: 'high',
          programs: ['wazuh', 'opnsense'],
          signals: 4,
          device_name: 'nas',
        },
      ])
      await turnOnAi(harness, aiSettings)
      await assistant.goto()
      await expect(assistant.empty).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await assistant.ask('What needs my attention right now?')
      await expect(assistant.answers).toContainText('Start with incident')
      await expect(assistant.busy).toHaveCount(0)
      await expectAccessible(page)

      await assistant.calls.last().click()
      await expect(assistant.callDialog).toBeVisible()
      await expectAccessible(page)
    })

    test('the agents, the sheet that makes one and the page of one, mid-run and finished, have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      aiSettings,
      agents,
      shell,
    }) => {
      await harness.createIncidents([
        {
          address: '93.184.216.34',
          severity: 'high',
          programs: ['wazuh', 'opnsense'],
          signals: 4,
          device_name: 'nas',
        },
      ])
      await turnOnAi(harness, aiSettings)
      await agents.goto()
      await expect(agents.empty).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await agents.make.click()
      await expect(agents.dialog).toBeVisible()
      await agents.chooseKind('Exposure scanner')
      await expect(agents.dialogActive).toBeVisible()
      // On a phone the sheet covers the buttons of the page under it, so only the sheet is checked.
      await expectAccessible(page, { include: '[data-test="agent-dialog"]' })
      await agents.chooseKind('Threat hunter')
      await agents.save.click()
      await expect(agents.dialog).toHaveCount(0)
      await expect(agents.cards).toHaveCount(1)
      await expectAccessible(page)

      await agents.cards.first().getByTestId('agent-run').click()
      await expect(agents.cards.first().getByTestId('agent-state')).toContainText(
        'Waiting to start',
      )
      await agents.cards.first().getByTestId('agent-open').click()
      await expect(agents.nodes.first()).toBeVisible()
      await expectAccessible(page)

      await harness.runAgents()
      await expect(agents.runStatus).toHaveText('Finished', { timeout: 15_000 })
      await expect(agents.findings).toHaveCount(1)
      await expectAccessible(page)
    })

    test('Settings > Agents, with their own provider and a limit set, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      aiSettings,
      agentSettings,
      shell,
    }) => {
      await harness.standIn({
        kind: 'anthropic',
        api_key: 'sk-a-key-for-the-stand-in',
        models: ['claude-haiku-5-5', 'claude-sonnet-5-5'],
        provider: 'anthropic',
      })
      await agentSettings.goto()
      await expect(agentSettings.state).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await agentSettings.source('own').check()
      await agentSettings.provider('anthropic').click()
      await aiSettings.apiKey('anthropic').fill('sk-a-key-for-the-stand-in')
      await aiSettings.test('anthropic').click()
      await expect(aiSettings.status('anthropic')).toHaveText('Connected')
      await agentSettings.daily.fill('2')
      await agentSettings.saveLimits.click()
      await expect(agentSettings.limitsSaved).toBeVisible()
      await expectAccessible(page)
    })

    test('the account settings page has no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
    }) => {
      await security.goto()
      await expect(security.twoFactorOff).toBeVisible()
      await expect(security.noPasskeys).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the password card, with what is wrong and what came of it, has no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
      baseline,
    }) => {
      await security.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await security.changePassword.click()
      await expect(security.passwordCard).toContainText('Enter your current password.')
      await expectAccessible(page)

      await security.changePasswordTo('not the right password', 'a different long phrase for tests')
      await expect(security.passwordCard).toContainText("The password isn't right.")
      await expectAccessible(page)

      await security.currentPassword.fill(baseline.account.password)
      await security.changePassword.click()
      await expect(security.passwordChanged).toBeVisible()
      await expectAccessible(page)
    })

    test('the sign-ins page, and the questions it asks, have no WCAG 2.2 AA problems', async ({
      page,
      signIns,
      shell,
      signInElsewhere,
    }) => {
      await signInElsewhere('Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Firefox/130.0')
      await signIns.goto()
      await expect(signIns.signIns).toHaveCount(2)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await signIns.endButtons.click()
      await expect(signIns.confirmTitle).toBeVisible()
      await expectAccessible(page)
      await signIns.cancel.click()
      await expect(signIns.confirmTitle).toBeHidden()

      await signIns.endOthers.click()
      await expect(signIns.confirmTitle).toBeVisible()
      await expectAccessible(page)
      await signIns.confirm.click()
      await expect(signIns.notice).toBeVisible()
      await expectAccessible(page)
    })

    test('the data page, and its questions, have no WCAG 2.2 AA problems', async ({
      page,
      data,
      shell,
    }) => {
      await data.goto()
      await expect(data.eventsCard.getByTestId('retention-source')).toHaveCount(5)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      // Once the theme menu has closed, bring the last row up: on a phone it starts under the
      // fixed bottom bar.
      await expect(page.getByTestId(`theme-${theme}`)).toBeHidden()
      await data.source(data.eventsCard, 'VirusTotal').evaluate((row) => {
        row.scrollIntoView({ block: 'center' })
      })
      await expectAccessible(page)

      await data.source(data.eventsCard, 'OPNsense').getByTestId('retention-change').click()
      await expect(data.dialogTitle).toBeVisible()
      // The page behind the dialog is covered while it is open, so these two checks look at the
      // dialog alone.
      await expectAccessible(page, { include: '[data-test="retention-dialog"]' })

      await data.useDays.check()
      await data.days.fill('0')
      await data.save.click()
      await expect(data.dialog).toContainText('Enter a whole number of days')
      await expectAccessible(page, { include: '[data-test="retention-dialog"]' })

      await data.days.fill('90')
      await data.save.click()
      await expect(data.eventsCard.getByTestId('retention-notice')).toBeVisible()
      await expectAccessible(page)
    })

    test('the data page’s charts, read and as tables, have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      integration,
      data,
      shell,
    }) => {
      await connectFirewall(harness, integration, [])
      await harness.setWorker('running')
      await harness.runCollectors()
      await data.goto()
      await expect(data.eventsChart).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await data.eventsChart.getByTestId('bar-slot').first().hover()
      await expect(data.eventsChart.getByTestId('chart-tooltip')).toBeVisible()
      await expectAccessible(page)

      await data.eventsChart.getByTestId('chart-view').click()
      await data.metricsChart.getByTestId('chart-view').click()
      await expect(data.eventsChart.getByTestId('chart-table')).toBeVisible()
      await expectAccessible(page)
    })

    test('the dashboard asking for attention, read and as tables, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      dashboard,
      shell,
    }) => {
      await harness.createActivity({
        collectors: ['ok', 'problem'],
        alerts: { critical: 1, high: 1, medium: 2, low: 1, info: 2 },
        blocked: { '203.0.113.9': 5, '198.51.100.7': 2 },
        traffic: { igc0: 80, igc1: 5 },
        devices: 2,
      })
      await harness.createIncidents([
        {
          address: '93.184.216.34',
          severity: 'critical',
          programs: ['wazuh', 'opnsense'],
          ban: true,
        },
        { address: '8.8.8.8', severity: 'low', programs: ['opnsense'], signals: 1 },
      ])
      await dashboard.goto()
      await expect(dashboard.banner).toHaveAttribute('data-state', 'attention')
      // What was left out, and the way to it, are there for the owner to see.
      await expect(dashboard.filteredUnsure).toHaveText('1 not sure enough')
      // The list of latest alerts is as long as it gets, with the incidents' alerts among them.
      await expect(dashboard.alertRows).toHaveCount(8)
      // The quiet scan is not sure enough to ask about, so only the attack is in the lane.
      await expect(dashboard.needsYouCards).toHaveCount(1)
      await expect(dashboard.noiseItems.first()).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await dashboard.trafficChart.getByRole('img').scrollIntoViewIfNeeded()
      const plot = await dashboard.trafficChart.getByRole('img').boundingBox()
      await page.mouse.move((plot?.x ?? 0) + (plot?.width ?? 0) * 0.9, (plot?.y ?? 0) + 80)
      await expect(dashboard.trafficChart.getByTestId('chart-tooltip')).toBeVisible()
      await expectAccessible(page)

      // The incident flagged above the lines, with what it says about it showing.
      await expect(dashboard.trafficFlags).toHaveCount(1)
      await page.mouse.move(0, 0)
      await expect(dashboard.trafficChart.getByTestId('chart-tooltip')).toBeHidden()
      await dashboard.trafficFlags.first().focus()
      await expect(dashboard.trafficChart.getByTestId('chart-tooltip')).toContainText('Began')
      await expectAccessible(page)

      for (const card of [dashboard.trafficCard, dashboard.alertsCard, dashboard.sourcesCard]) {
        await card.getByTestId('chart-view').click()
        await expect(card.getByTestId('chart-table')).toBeVisible()
      }
      await expectAccessible(page)
    })

    for (const [state, collectors] of [
      ['setup', []],
      ['calm', ['ok']],
      ['watch', ['problem']],
    ] as const) {
      test(`the dashboard saying ${state} has no WCAG 2.2 AA problems`, async ({
        page,
        harness,
        dashboard,
        shell,
      }) => {
        await harness.createActivity({ collectors: [...collectors] })
        await dashboard.goto()
        await expect(dashboard.banner).toHaveAttribute('data-state', state)
        await shell.chooseTheme(theme)
        await shell.expectTheme(theme)

        await expectAccessible(page)
      })
    }

    test('the status page, and its warning, have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      integration,
      status,
      shell,
    }) => {
      await status.goto()
      await expect(status.fine).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      // A part with a problem turns the all clear into a warning, and its row into an error.
      const ntopng = await harness.standIn({ kind: 'ntopng', token: 'a-valid-ntopng-token' })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill('the wrong token')
      await integration.save.click()
      await expect(integration.status).toHaveText('Problem')
      // The collector worker and a collector with a problem are listed too.
      await harness.setWorker('running')
      await harness.runCollectors()
      await status.goto()
      await expect(status.attention).toBeVisible()
      await expect(status.collectorStates).toHaveText(['Working', ...new Array(4).fill('Problem')])
      await expectAccessible(page)

      await status.copy.click()
      await expect(status.copied.or(status.copyFailed)).toBeVisible()
      await expectAccessible(page)
    })

    test('the activity page has no WCAG 2.2 AA problems', async ({ page, activity, shell }) => {
      await activity.goto()
      await expect(activity.entries.first()).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the passkeys card, adding one and removing one have no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
      authenticator,
      baseline,
    }) => {
      await security.goto()
      await expect(security.noPasskeys).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await security.addPasskey.click()
      await expect(security.newPasskeyName).toBeVisible()
      await expectAccessible(page)

      await security.passkeyPassword.fill('not the password')
      await security.createPasskey.click()
      await expect(security.passkeysError).toBeVisible()
      await expectAccessible(page)

      await security.passkeyPassword.fill(baseline.account.password)
      await security.createPasskey.click()
      await expect(security.passkeyNames).toHaveCount(1)
      expect(await authenticator.passkeys()).toHaveLength(1)
      await expectAccessible(page)

      await security.removePasskeyButtons.click()
      await expect(security.confirmRemovePasskey).toBeVisible()
      await expectAccessible(page)
    })

    test('adding an authenticator app has no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
    }) => {
      await security.goto()
      await expect(security.twoFactorOff).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await security.addApp.click()
      await expect(security.key).toBeVisible()
      await expectAccessible(page)

      await security.confirmCode.fill('000000')
      await security.confirm.click()
      await expect(security.twoFactorError).toBeVisible()
      await expectAccessible(page)
    })

    test('the recovery codes and the card when it is on have no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
    }) => {
      await security.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await security.addApp.click()
      const secret = ((await security.key.textContent()) ?? '').replaceAll(/\s/g, '')
      await security.confirmCode.fill(authenticatorCode(secret))
      await security.confirm.click()
      await expect(security.recoveryCodeItems).toHaveCount(10)
      await expectAccessible(page)

      await security.codesSaved.check()
      await security.codesDone.click()
      await expect(security.twoFactorOn).toBeVisible()
      await expectAccessible(page)
    })

    test('making new codes and turning it off have no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
    }) => {
      await security.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await security.addAuthenticator()

      await security.renewCodes.click()
      await expect(security.renewCode).toBeVisible()
      await expectAccessible(page)
      await security.cancel.click()

      await security.turnOff.click()
      await expect(security.turnOffPassword).toBeVisible()
      await expectAccessible(page)
    })

    test('the second step of signing in has no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
      signIn,
      baseline,
    }) => {
      await security.goto()
      await security.addAuthenticator()
      await shell.signOutFromMenu()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await signIn.signIn(baseline.account)
      await expect(signIn.code).toBeVisible()
      await expectAccessible(page)

      await signIn.enterCode('000000')
      await expect(signIn.error).toBeVisible()
      await expectAccessible(page)
    })

    test('the account menu has no WCAG 2.2 AA problems', async ({ page, dashboard, shell }) => {
      await dashboard.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await shell.userMenu.click()
      await expect(shell.signOut).toBeVisible()

      await expectAccessible(page)
    })

    test.describe('before signing in', () => {
      test.use({ signedIn: false })

      test('the sign-in page has no WCAG 2.2 AA problems', async ({ page, signIn, shell }) => {
        await signIn.goto()
        await shell.chooseTheme(theme)
        await shell.expectTheme(theme)

        await expectAccessible(page)
      })

      test('the sign-in page with an error has no WCAG 2.2 AA problems', async ({
        page,
        signIn,
        shell,
        baseline,
      }) => {
        await signIn.goto()
        await shell.chooseTheme(theme)
        await shell.expectTheme(theme)
        await signIn.signIn({ ...baseline.account, password: 'not the right password' })
        await expect(signIn.error).toBeVisible()

        await expectAccessible(page)
      })

      test('both steps of setting up have no WCAG 2.2 AA problems', async ({
        page,
        harness,
        setup,
        shell,
        baseline,
      }) => {
        await harness.loadFixture('fresh-install')
        await setup.goto()
        await shell.chooseTheme(theme)
        await shell.expectTheme(theme)
        await expectAccessible(page)

        await setup.enterCode(baseline.fresh_install_setup_code)
        await expect(setup.step).toHaveText(/^Step 2 of 2/)
        await expectAccessible(page)

        await setup.createAccountWith({ username: 'x', password: 'short' }, 'different')
        await expect(page.getByText("The passwords don't match.")).toBeVisible()
        await expectAccessible(page)
      })
    })

    test('the theme menu has no WCAG 2.2 AA problems', async ({ page, dashboard, shell }) => {
      await dashboard.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await shell.themeToggle.click()
      await expect(page.getByTestId('theme-system')).toBeVisible()

      await expectAccessible(page)
    })

    test('the command palette, listing everything, narrowed and finding nothing, has no WCAG 2.2 AA problems', async ({
      page,
      dashboard,
      shell,
    }) => {
      await dashboard.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await shell.openPaletteWithKeys()
      await expect(shell.paletteRows.first()).toBeVisible()
      await expectAccessible(page)

      await page.keyboard.press('ArrowDown')
      await expect(shell.paletteRows.first()).toBeFocused()
      await expectAccessible(page)

      await shell.paletteSearch.fill('93.184.216.34')
      await expect(shell.paletteRows).toHaveCount(1)
      await expectAccessible(page)

      await shell.paletteSearch.fill('zzzz')
      await expect(shell.paletteEmpty).toBeVisible()
      await expectAccessible(page)
    })

    test('the integrations list has no WCAG 2.2 AA problems', async ({
      page,
      integrations,
      shell,
    }) => {
      await integrations.goto()
      await expect(integrations.names).toHaveCount(5)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the setup instructions have no WCAG 2.2 AA problems', async ({
      page,
      integration,
      shell,
    }) => {
      // Two connections, one of them optional, so every part of the window is drawn.
      await integration.goto('opnsense')
      await expect(integration.title).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await integration.guideOpen.click()
      await expect(integration.guide).toBeVisible()
      await expectAccessible(page)

      await integration.guide.getByTestId('guide-sources').scrollIntoViewIfNeeded()
      await expectAccessible(page)
    })

    test('the interfaces, their sheet and the page of one have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      interfaces,
      shell,
    }) => {
      await harness.createFeeds([
        { native_name: 'igc0', interface: 'Internet', role: 'internet' },
        { native_name: 'guest' },
        { native_name: 'igc7' },
      ])
      await harness.createActivity({ traffic: { igc0: 8 } })
      await interfaces.goto()
      await expect(interfaces.cards).toHaveCount(1)
      await expect(interfaces.suggestions).toHaveCount(1)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      // Where a feed can go, with the list open.
      await interfaces.feed('igc7').getByTestId('feed-move').click()
      await expect(page.getByRole('option').first()).toBeVisible()
      await expectAccessible(page)
      await page.keyboard.press('Escape')

      // The sheet that makes an interface, with a role chosen.
      await interfaces.add.click()
      await expect(interfaces.editor).toBeVisible()
      await interfaces.chooseRole('Guests')
      await expectAccessible(page)
      await page.keyboard.press('Escape')
      await expect(interfaces.editor).toHaveCount(0)

      // The page of one interface.
      await interfaces.card('Internet').click()
      await expect(page.getByTestId('interface-chart')).toBeVisible()
      await expectAccessible(page)
    })

    test('the alerts, their dialog with a mistake in it, and the question about removing one have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      alerts,
      shell,
    }) => {
      // The stand-in knows one webhook, so the second one is turned away and shows a problem.
      const id = '1234567890123456789'
      const token = 'Zk3-_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_x'
      await harness.standIn({ kind: 'discord', webhook: `${id}/${token}` })
      await alerts.goto()
      await expect(alerts.empty).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await alerts.addDestination(
        'Security channel',
        `https://discord.com/api/webhooks/${id}/${token}`,
      )
      await alerts.destination('Security channel').getByTestId('destination-test').click()
      await expect(alerts.destination('Security channel').getByTestId('status')).toHaveText(
        'Connected',
      )
      await alerts.addDestination(
        'Family',
        'https://discord.com/api/webhooks/9876543210987654321/Qq9-_zyxwvutsrqponmlkjihgfedcba',
      )
      await alerts.destination('Family').getByTestId('destination-test').click()
      await expect(alerts.destination('Family').getByTestId('status')).toHaveText('Problem')
      await expect(alerts.destination('Family').getByTestId('destination-result')).toBeVisible()
      await expectAccessible(page)

      // The dialog, with an address that is refused and said so in words.
      await alerts.add.click()
      await alerts.name.fill('Somewhere')
      await alerts.url.fill('https://example.com/api/webhooks/1234567890123456789/abcdefghijklmnop')
      await alerts.save.click()
      await expect(alerts.dialog).toContainText("That isn't a Discord address.")
      await expectAccessible(page)
      await alerts.cancel.click()
      await expect(alerts.dialog).toHaveCount(0)

      // The question, with a destination that is turned off behind it.
      await alerts.destination('Family').getByTestId('destination-remove').click()
      await expect(alerts.confirmTitle).toBeVisible()
      await expectAccessible(page)
    })

    test('the rules of a destination, with a preview, quiet hours and a mistake, have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      alerts,
      shell,
    }) => {
      await harness.createIncidents([
        {
          address: '93.184.216.34',
          severity: 'critical',
          programs: ['wazuh', 'opnsense'],
          signals: 6,
          minutes_ago: 4,
        },
        { address: '8.8.8.8', severity: 'high', programs: ['opnsense'], signals: 3 },
        { address: '9.9.9.9', severity: 'low', programs: ['opnsense'], status: 'resolved' },
      ])
      await alerts.goto()
      await alerts.addDestination(
        'Security channel',
        'https://discord.com/api/webhooks/1234567890123456789/Zk3-_abcdefghijklmnopqrstuvwxyz',
      )
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expect(alerts.destination('Security channel')).toBeVisible()
      await expectAccessible(page)

      // The sheet, with the cards for what the channel is for, what the rules would have done and
      // what was left out, and the message as Discord will show it.
      await alerts.openRules('Security channel')
      await expect(alerts.previewSummary).toContainText('would have sent')
      await expect(alerts.previewLeftOut).toBeVisible()
      await expect(alerts.purposeChosen('threats')).toBeChecked()
      await expect(alerts.discordTitle).toBeVisible()
      await expectAccessible(page)

      // With the later message of the story, which has a title of its own.
      await alerts.story('worse').click()
      await expect(alerts.discordTitle).toContainText('Escalated')
      await expectAccessible(page)

      // Custom rules, with the rest of the choices open.
      await alerts.changeRules(() => alerts.purpose('custom').click())
      await expect(alerts.floors).toBeVisible()
      await expectAccessible(page)

      // With quiet hours on, and a start that is also the end, which can't be saved.
      await alerts.changeRules(async () => {
        await alerts.quiet.check()
        await alerts.quietFrom.fill('22:00')
        await alerts.quietUntil.fill('22:00')
      })
      await expect(alerts.rulesSave).toBeDisabled()
      await expectAccessible(page)

      // With a menu open.
      await alerts.severity.locator('.v-field').click()
      await expect(page.getByRole('option').first()).toBeVisible()
      await expectAccessible(page)
      await page.keyboard.press('Escape')

      // With the page it could not reach.
      await page.route('**/api/alerts/destinations/*/rules', (route) => route.abort())
      await alerts.changeRules(() => alerts.quietUntil.fill('07:00'))
      await alerts.rulesSave.click()
      await expect(alerts.rulesFailure).toBeVisible()
      await expectAccessible(page)
    })

    test('an integration, with its mistakes and its log, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      integration,
      shell,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: 'a-valid-token' })
      await integration.goto('ntopng')
      await expect(integration.title).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await integration.address('api').fill('http://8.8.8.8:3000')
      await integration.field('api', 'token').fill('a-token')
      await integration.save.click()
      await expect(integration.problems).toBeVisible()
      await expectAccessible(page)

      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill('the wrong token')
      await integration.save.click()
      await expect(integration.report).toContainText('The test failed')
      await expect(integration.logCalls).toHaveCount(1)
      await expectAccessible(page)

      await integration.field('api', 'token').fill('a-valid-token')
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')
      await expectAccessible(page)

      // The interfaces ntopng lists, with the one that has seen nothing chosen as well and said
      // so, and the list open and closed.
      await integration.lookupFetch('api').click()
      await expect(integration.lookupMessage('api')).toBeVisible()
      await integration.lookupSelect('api').click()
      await page.getByRole('option').nth(1).click()
      await expect(integration.lookupQuiet('api')).toBeVisible()
      await expect(page.getByRole('option')).toHaveCount(2)
      await expectAccessible(page)
      await page.keyboard.press('Escape')
      await expectAccessible(page)

      // The collection card, whether the worker has reported in or not, and with a job listed.
      await expect(integration.collectionWorker).toBeVisible()
      await expectAccessible(page)
      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()
      await expect(integration.collectorStates).toHaveText(new Array(4).fill('Working'))
      await expectAccessible(page)

      await integration.disconnect.click()
      await expect(integration.confirmation).toBeVisible()
      await expectAccessible(page)
    })

    test('Wazuh, with what its certificates need said beside the choice, has no WCAG 2.2 AA problems', async ({
      page,
      integration,
      shell,
    }) => {
      await integration.goto('wazuh')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expect(integration.certificateNote('manager')).toBeVisible()
      await expect(integration.certificateNote('indexer')).toBeVisible()
      await expectAccessible(page)

      await integration.tlsMode('indexer', 'ca').check()
      await expect(integration.authority('indexer')).toBeVisible()
      await expectAccessible(page)
    })

    test('OPNsense, with its certificate, services and Zenarmor, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      integration,
      shell,
    }) => {
      const firewall = await harness.standIn({
        kind: 'opnsense',
        api_key: 'a-key',
        api_secret: 'a-secret',
        services: ['suricata', 'openvpn'],
      })
      await integration.goto('opnsense')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await integration.address('api').fill(firewall.url)
      await integration.field('api', 'api_key').fill('a-key')
      await integration.field('api', 'api_secret').fill('a-secret')
      await integration.tlsMode('api', 'pinned').check()
      await integration.lookUp('api').click()
      await expect(integration.found('api')).toBeVisible()
      await expectAccessible(page)

      await integration.trust('api').click()
      await integration.save.click()
      await expect(integration.module('api', 'Suricata')).toContainText('Running')
      await expectAccessible(page)

      await integration.useConnection('zenarmor').check()
      await expect(integration.address('zenarmor')).toBeVisible()
      await expectAccessible(page)
    })

    test('a certificate that is looked up, one that fails a test and one that has changed have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      integration,
      shell,
    }) => {
      const firewall = await harness.standIn({
        kind: 'opnsense',
        api_key: 'a-key',
        api_secret: 'a-secret',
        services: [],
      })
      await integration.goto('opnsense')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await integration.address('api').fill(firewall.url)
      await integration.field('api', 'api_key').fill('a-key')
      await integration.field('api', 'api_secret').fill('a-secret')

      // Looked up before anything is saved: the certificate, why it isn't accepted, the button.
      await integration.lookUp('api').click()
      await expect(integration.verdict('api')).toBeVisible()
      await expect(integration.trust('api')).toBeVisible()
      await expectAccessible(page)

      // A test that fails over it, with the way to review it where the failure is said.
      await integration.save.click()
      await expect(integration.report).toContainText('The test failed')
      await expect(integration.reviewCertificate('api')).toBeVisible()
      await expect(integration.reviewFromReport()).toBeVisible()
      await expectAccessible(page)

      // Reviewed from there, ready to be trusted and tested, then trusted.
      await integration.reviewCertificate('api').click()
      await expect(integration.trustAndTest('api')).toBeVisible()
      await expectAccessible(page)
      await integration.trustAndTest('api').click()
      await expect(integration.trusted('api')).toBeVisible()
      await expect(integration.report).toContainText('The test passed')
      await expectAccessible(page)

      // The certificate changes: the failure, and the new one beside the same decision.
      const trusted = await integration.fingerprint('api').inputValue()
      await integration.fingerprint('api').fill(trusted.replace(/[0-9a-f]/gi, '0'))
      await integration.save.click()
      await expect(integration.report).toContainText('The certificate has changed')
      await integration.reviewFromReport().click()
      await expect(integration.verdict('api')).toContainText('The certificate has changed')
      await expectAccessible(page)
    })
  })
}

test.describe('theme', () => {
  test('keeps the choice after a reload', async ({ page, dashboard, shell }) => {
    await dashboard.goto()
    await shell.chooseTheme('dark')
    await shell.expectTheme('dark')

    await page.reload()

    await shell.expectTheme('dark')
  })

  test('still works when the browser will not store settings', async ({
    page,
    dashboard,
    shell,
  }) => {
    await page.addInitScript(() => {
      const refuse = () => {
        throw new DOMException('Storage is off', 'SecurityError')
      }
      Storage.prototype.getItem = refuse
      Storage.prototype.setItem = refuse
    })
    await page.emulateMedia({ colorScheme: 'light' })
    await dashboard.goto()
    await shell.expectTheme('light')

    await shell.chooseTheme('dark')

    await shell.expectTheme('dark')
  })

  test('follows the browser when the choice is System', async ({ page, dashboard, shell }) => {
    await page.emulateMedia({ colorScheme: 'dark' })
    await dashboard.goto()
    await shell.chooseTheme('system')
    await shell.expectTheme('dark')

    await page.emulateMedia({ colorScheme: 'light' })

    await shell.expectTheme('light')
  })
})
