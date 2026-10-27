import { authenticatorCode, connectFirewall, expect, expectAccessible, test } from '../support'

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
      await expect(data.eventsCard.getByTestId('retention-source')).toHaveCount(4)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await data.source(data.eventsCard, 'OPNsense').getByTestId('retention-change').click()
      await expect(data.dialogTitle).toBeVisible()
      await expectAccessible(page)

      await data.useDays.check()
      await data.days.fill('0')
      await data.save.click()
      await expect(data.dialog).toContainText('Enter a whole number of days')
      await expectAccessible(page)

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
      // The list of latest alerts is as long as it gets, with the incidents' alerts among them.
      await expect(dashboard.alertRows).toHaveCount(8)
      await expect(dashboard.needsYouCards).toHaveCount(2)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await dashboard.trafficChart.getByRole('img').scrollIntoViewIfNeeded()
      const plot = await dashboard.trafficChart.getByRole('img').boundingBox()
      await page.mouse.move((plot?.x ?? 0) + (plot?.width ?? 0) * 0.9, (plot?.y ?? 0) + 80)
      await expect(dashboard.trafficChart.getByTestId('chart-tooltip')).toBeVisible()
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
      await expect(integrations.names).toHaveCount(4)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

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
