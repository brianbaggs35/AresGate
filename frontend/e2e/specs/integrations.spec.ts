import {
  connectFirewall,
  expect,
  FIREWALL_KEY as KEY,
  FIREWALL_SECRET as SECRET,
  test,
} from '../support'

const TOKEN = 'a-valid-ntopng-token'
const USERNAME = 'aresgate'
const PASSWORD = 'a-valid-password'

test.describe('integrations', () => {
  test('lists a card for each, which opens its own page', async ({
    page,
    shell,
    integrations,
    integration,
  }) => {
    await page.goto('/')

    await shell.goTo('integrations')

    await expect(page).toHaveURL('/integrations')
    await expect(page).toHaveTitle('Integrations · AresGate')
    await expect(integrations.heading).toBeVisible()
    await expect(integrations.names).toHaveText([
      'OPNsense',
      'ntopng',
      'Wazuh',
      'CrowdSec',
      'VirusTotal',
      'AlienVault OTX',
      'GreyNoise',
      'NIST NVD',
      'Fingerbank',
    ])
    await expect(integrations.count).toHaveText('0 of 9 set up')
    for (const key of [
      'opnsense',
      'ntopng',
      'wazuh',
      'crowdsec',
      'virustotal',
      'otx',
      'greynoise',
      'fingerbank',
    ]) {
      await expect(integrations.status(key)).toHaveText('Not connected')
      await expect(integrations.lastCall(key)).toHaveText('Not set up yet')
    }
    await shell.expectCurrent('integrations')

    await integrations.card('ntopng').click()

    await expect(page).toHaveURL('/integrations/ntopng')
    await expect(integration.title).toHaveText('ntopng')
    await expect(integration.status).toHaveText('Not connected')
    // The place in the menu stays marked on the integration's own page.
    await shell.expectCurrent('integrations')

    await integration.back.click()

    await expect(page).toHaveURL('/integrations')
    await expect(integrations.names).toHaveCount(9)
  })

  test('explains how to get what is needed in a window, and links to the official documentation', async ({
    page,
    integration,
  }) => {
    await integration.goto('ntopng')

    await expect(integration.docs).toHaveAttribute('href', /^https:\/\/www\.ntop\.org\//)
    await expect(integration.docs).toHaveAttribute('target', '_blank')
    await expect(integration.docs).toHaveAttribute('rel', 'noopener noreferrer')
    await expect(integration.guide).toBeHidden()

    await integration.guideOpen.click()

    await expect(integration.guideTitle).toHaveText('Set up ntopng')
    // The menus, the user's role and the token, named as ntopng names them.
    await expect(integration.guide).toContainText('Manage Users')
    await expect(integration.guide).toContainText('Non Privileged User')
    await expect(integration.guide).toContainText('User Authentication Token')
    await expect(integration.guideStepTitles).toHaveText([
      'Open user management',
      'Add a user for AresGate',
      "Generate the user's token",
      'Connect and choose the interfaces',
    ])
    // The pages it comes from are linked, and open in a tab of their own.
    await expect(integration.guideSources.first()).toHaveAttribute(
      'href',
      /^https:\/\/www\.ntop\.org\//,
    )
    await expect(integration.guideSources.first()).toHaveAttribute('target', '_blank')

    await integration.guideDone.click()

    await expect(integration.guide).toBeHidden()
    await expect(page).toHaveURL('/integrations/ntopng')
  })

  test('has instructions for every connection of every integration, from its own documentation', async ({
    integration,
  }) => {
    const connections = {
      opnsense: ['api', 'zenarmor'],
      ntopng: ['api'],
      wazuh: ['manager', 'indexer'],
      crowdsec: ['lapi'],
      virustotal: ['api'],
      otx: ['api'],
      fingerbank: ['api'],
    }
    for (const [key, parts] of Object.entries(connections)) {
      await integration.goto(key)
      await integration.guideOpen.click()

      for (const part of parts) await expect(integration.guidePart(part)).toBeVisible()
      await expect(integration.guideSteps.first()).toBeVisible()
      expect(await integration.guideSources.count()).toBeGreaterThan(0)
      await integration.guideClose.click()
      await expect(integration.guide).toBeHidden()
    }
  })

  test('moves the keyboard into the instructions, closes them with Escape and gives it back', async ({
    page,
    integration,
  }) => {
    await integration.goto('crowdsec')
    await integration.guideOpen.focus()
    await page.keyboard.press('Enter')

    await expect(integration.guide).toBeVisible()
    await expect(integration.guideTitle).toBeFocused()
    const inside = () =>
      page.evaluate(() => document.activeElement?.closest('.v-overlay__content') != null)
    // Tab stays inside the window, however many times it is pressed.
    for (let press = 0; press < 12; press++) await page.keyboard.press('Tab')
    expect(await inside()).toBe(true)

    await page.keyboard.press('Escape')

    await expect(integration.guide).toBeHidden()
    await expect(integration.guideOpen).toBeFocused()
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
    await expect(integrations.names).toHaveCount(9)
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
      // Nothing was chosen, so it reads every interface ntopng lists.
      await expect(integration.report).toContainText(
        'ntopng answered. No interface is chosen, so AresGate reads every one ntopng lists. Interface 0 is eth0: 41 hosts (18 local), 212 flows, 1.0 GB seen.',
      )
      await expect(integration.status).toHaveText('Connected')
      await expect(integration.save).toHaveText('Save and test')
      await expect(integration.connectionStatus('api')).toHaveText('Connected')
      await expect(integration.lastSuccess).toContainText('Last successful call')
      // The log has the requests, newest first, with their paths and no query string, and how
      // they went: the interfaces ntopng has, then what each has seen (the test), and the same
      // again for the list under Interfaces, which is asked for again after a test that passed.
      await expect(integration.logCalls).toHaveCount(6)
      await expect(integration.logCalls.first()).toContainText(
        '/lua/rest/v2/get/interface/data.lua',
      )
      await expect(integration.logCalls.last()).toContainText(
        '/lua/rest/v2/get/ntopng/interfaces.lua',
      )
      await expect(integration.logCalls.last()).toContainText('200')
      await expect(integration.logCalls.last().getByRole('img')).toHaveAttribute(
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
      await expect(integrations.count).toHaveText('1 of 9 set up')
    })

    test('names the interfaces before anything is saved, and says which has seen nothing', async ({
      page,
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      // There is nothing to ask until the address is there.
      await expect(integration.lookupFetch('api')).toBeDisabled()
      await expect(integration.lookupNeedsAddress('api')).toBeVisible()

      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)
      await expect(integration.lookupFetch('api')).toBeEnabled()
      await integration.lookupFetch('api').click()

      await expect(integration.lookupMessage('api')).toHaveText('ntopng lists 2 interfaces.')
      // Nothing was chosen, so both are, and the quiet one is said to have seen nothing.
      await expect(integration.lookupSelect('api')).toContainText('eth0')
      await expect(integration.lookupSelect('api')).toContainText('LAN (eth1)')
      await expect(integration.lookupQuiet('api')).toBeVisible()
      // Each is named, with its ID, where its traffic comes from and what it has seen.
      await integration.lookupSelect('api').click()
      const options = page.getByRole('option')
      await expect(options).toHaveCount(2)
      await expect(options.nth(0)).toContainText('eth0')
      await expect(options.nth(0)).toContainText(
        'ID 0 · live packet capture · 41 hosts (18 local), 212 flows, 1.0 GB seen',
      )
      await expect(options.nth(1)).toContainText('LAN (eth1)')
      await expect(options.nth(1)).toContainText('ID 1 · live packet capture · no traffic seen yet')
      // More than one can be chosen: LAN comes off, and joins again.
      await options.nth(1).click()
      await page.keyboard.press('Escape')
      await expect(integration.lookupSelect('api')).not.toContainText('LAN (eth1)')
      await expect(integration.lookupQuiet('api')).toHaveCount(0)
      // The list has closed before it is opened again, so the option isn't still moving.
      await expect(options).toHaveCount(0)
      await integration.lookupSelect('api').locator('.v-field').click()
      await expect(options).toHaveCount(2)
      await options.nth(1).click()
      await page.keyboard.press('Escape')
      await expect(integration.lookupSelect('api')).toContainText('eth0')
      await expect(integration.lookupSelect('api')).toContainText('LAN (eth1)')
      await expect(integration.lookupQuiet('api')).toHaveText(
        "LAN (eth1) hasn't seen any traffic yet, so nothing will come in from it until it does.",
      )
      // Nothing was saved by asking, and the requests are in the log.
      await expect(integration.status).toHaveText('Not connected')
      await integration.logRefresh.click()
      await expect(integration.logCalls).toHaveCount(3)

      await integration.save.click()

      await expect(integration.report).toContainText('The test passed')
      await expect(integration.report).toContainText(
        "ntopng answered. Interface 0 is eth0: 41 hosts (18 local), 212 flows, 1.0 GB seen. Interface 1 is LAN (eth1) and hasn't seen any traffic yet.",
      )
      await expect(integration.status).toHaveText('Connected')

      // The next visit names the interfaces at once, and both are still chosen.
      await page.reload()
      await expect(integration.lookupMessage('api')).toHaveText('ntopng lists 2 interfaces.')
      await expect(integration.lookupSelect('api')).toContainText('eth0')
      await expect(integration.lookupSelect('api')).toContainText('LAN (eth1)')
      await expect(integration.lookupQuiet('api')).toBeVisible()

      // Taking the quiet one off is saved and tested like any other setting.
      await integration.lookupSelect('api').click()
      await page.getByRole('option').nth(1).click()
      await page.keyboard.press('Escape')
      await expect(integration.lookupQuiet('api')).toHaveCount(0)
      await integration.save.click()
      await expect(integration.report).toContainText('Interface 0 is eth0: 41 hosts')
      await expect(integration.report).not.toContainText('Interface 1')
    })

    test('starts on every interface but the loopback when nothing is chosen', async ({
      page,
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)
      await page.route('**/api/integrations/ntopng/connections/api/lookup/interface_id', (route) =>
        route.fulfill({
          json: {
            ok: true,
            message: 'ntopng lists 3 interfaces.',
            entries: [
              {
                value: '5',
                label: 'quiet',
                detail: 'no traffic seen yet',
                quiet: true,
                loopback: false,
              },
              { value: '6', label: 'busy', detail: '3 hosts', quiet: false, loopback: false },
              { value: '7', label: 'busier', detail: '9 hosts', quiet: false, loopback: false },
              { value: '8', label: 'lo0', detail: 'loopback', quiet: false, loopback: true },
            ],
          },
        }),
      )

      await integration.lookupFetch('api').click()

      await expect(integration.lookupSelect('api')).toContainText('busy')
      await expect(integration.lookupSelect('api')).toContainText('busier')
      await expect(integration.lookupSelect('api')).toContainText('quiet')
      await expect(integration.lookupSelect('api')).not.toContainText('lo0')
      await expect(integration.lookupQuiet('api')).toBeVisible()
    })

    test('works with a ntopng that numbers its interfaces from 1, and mends an old choice of 0 in one click', async ({
      page,
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN, firewall: true })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)

      // Nothing is chosen, so it reads every interface but the loopback, which has no ID 0 to
      // trip over.
      await integration.save.click()
      await expect(integration.report).toContainText('The test passed')
      await expect(integration.report).toContainText(
        'No interface is chosen, so AresGate reads every one ntopng lists but the loopback.',
      )
      await expect(integration.report).toContainText('Interface 1 is WAN (igc0)')
      await expect(integration.report).toContainText('Interface 2 is LAN (igc1)')
      await expect(integration.report).toContainText('Interface 6 is ovpns1')
      await expect(integration.report).not.toContainText('lo0')
      // The field says the same once the list is known, without pressing Fetch interfaces.
      await expect(integration.lookupDefault('api')).toContainText(
        'Nothing is chosen, so AresGate reads WAN (igc0), LAN (igc1), and ovpns1. lo0 is the loopback, which normally has nothing worth reading.',
      )

      // The loopback can still be chosen, and is said to be normally not worth reading.
      await integration.lookupSelect('api').click()
      const options = page.getByRole('option')
      await expect(options).toHaveCount(4)
      await expect(options.nth(2)).toContainText('lo0')
      await expect(options.nth(2)).toContainText('loopback, normally not useful')
      await options.nth(2).click()
      await page.keyboard.press('Escape')
      await expect(integration.lookupLoopback('api')).toHaveText(
        'lo0 is the loopback, which normally has nothing worth reading.',
      )
    })

    test('says what ntopng has when the saved choice is 0, and mends it in one click', async ({
      page,
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN, firewall: true })
      // What a connection saved before there was no default of 0 holds.
      await page.route('**/api/integrations/ntopng', async (route) => {
        if (route.request().method() !== 'PUT') return route.fallback()
        const body = route.request().postDataJSON() as {
          connections: { api: { options: Record<string, string> } }
        }
        body.connections.api.options.interface_id = '0'
        return route.continue({ postData: JSON.stringify(body) })
      })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill(TOKEN)
      await integration.save.click()

      // The test names what ntopng has, flags the loopback, and says which to choose.
      await expect(integration.report).toContainText('The test failed')
      await expect(integration.report).toContainText(
        'ntopng answered, but has no interface with ID 0. It has: ID 1: WAN (igc0), ID 2: LAN (igc1), ID 3: lo0 (loopback), ID 6: ovpns1.',
      )
      await expect(integration.report).toContainText('Suggested: IDs 1, 2 and 6.')
      await expect(integration.status).toHaveText('Problem')

      // The next visit lists the interfaces at once, and offers to choose them in one click.
      await page.unroute('**/api/integrations/ntopng')
      await page.reload()
      await expect(integration.lookupGone('api')).toContainText(
        "The saved choice (ID 0) isn't on the list REST API gave now.",
      )
      await expect(integration.lookupMend('api')).toHaveText(
        'Use WAN (igc0), LAN (igc1), and ovpns1',
      )
      await integration.lookupMend('api').click()
      await expect(integration.lookupGone('api')).toHaveCount(0)
      await expect(integration.lookupSelect('api')).toContainText('WAN (igc0)')
      await expect(integration.lookupSelect('api')).toContainText('ovpns1')
      await expect(integration.lookupSelect('api')).not.toContainText('lo0')

      await integration.save.click()
      await expect(integration.report).toContainText('The test passed')
      await expect(integration.report).toContainText('Interface 1 is WAN (igc0)')
      await expect(integration.report).toContainText('Interface 6 is ovpns1')
      await expect(integration.status).toHaveText('Connected')
    })

    test('says why the interfaces could not be listed, and what to fix first', async ({
      harness,
      integration,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)

      // No token yet: the API says what is missing, in a sentence.
      await integration.lookupFetch('api').click()
      await expect(integration.lookupError('api')).toContainText(
        'Fill in the connection first. Authentication token: Enter a value.',
      )

      // A token ntopng refuses is ntopng's answer, in words, and the choice stays as it was.
      await integration.field('api', 'token').fill('the wrong token')
      await integration.lookupFetch('api').click()
      await expect(integration.lookupError('api')).toContainText(
        'ntopng redirected to its login page',
      )
      await expect(integration.lookupMessage('api')).toHaveCount(0)
      await expect(integration.lookupSelect('api')).not.toContainText('ID ')

      // The right one clears it.
      await integration.field('api', 'token').fill(TOKEN)
      await integration.lookupFetch('api').click()
      await expect(integration.lookupError('api')).toHaveCount(0)
      await expect(integration.lookupMessage('api')).toBeVisible()
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
      await expect(integration.collectors).toHaveCount(4)
      await expect(integration.collectors).toContainText([
        'Connection check',
        'Alerts',
        'Hosts',
        'Interface traffic',
      ])
      await expect(integration.collectorStates).toHaveText(new Array(4).fill('Working'))
      await expect(integration.collectorTimings.first()).toContainText('Last ran just now')
      await expect(integration.collectorTimings.first()).toContainText('next run in 5 minutes')
      await expect(integration.collectorTimings.nth(1)).toContainText('next run within a minute')
      await expect(integration.collectorErrors).toHaveCount(0)
      // The collectors' requests are in the log with the ones made from this page: the check
      // (the interfaces, then what each has seen, from the page, again for the list under
      // Interfaces and again from the collector), and for every other collector, its own. With
      // no interface chosen each asks which ntopng has, and the alerts collector asks again for
      // the names it keeps with each alert.
      await integration.logRefresh.click()
      await expect(integration.logCalls).toHaveCount(21)
    })

    test('keeps its alerts, its hosts and the devices among them, and measures its interface', async ({
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

      // Two alerts for flows and two for hosts of the last half hour; the older one is left out.
      expect((await harness.rowCounts()).events).toBe(4)
      // Five readings of each of the three local hosts, and twelve of the interface.
      expect((await harness.rowCounts()).metric_samples).toBe(27)
      // The two hosts in the broadcast domain, and not the one behind the router.
      expect((await harness.rowCounts()).devices).toBe(2)
      await harness.runCollectors()
      expect((await harness.rowCounts()).events).toBe(4)
      expect((await harness.rowCounts()).metric_samples).toBe(54)
      expect((await harness.rowCounts()).devices).toBe(2)
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
      await expect(integration.collectorStates).toHaveText(new Array(4).fill('Problem'))
      await expect(integration.collectorErrors).toContainText(
        new Array(4).fill('ntopng redirected to its login page'),
      )
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
      await expect(integration.collectors).toHaveCount(4)
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
      // The refused token made one request, and the one that works six (what the test asks and
      // what the list under Interfaces asks, which is the interfaces and each one's traffic).
      await expect(integration.logCalls).toHaveCount(7)
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
      await expect(integration.logCalls).toHaveCount(6)
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
      await expect(integration.logCalls).toHaveCount(6)
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
      await expect(integration.logCalls).toHaveCount(6)
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

    test('keeps the bans made here and counts how many are in force', async ({
      harness,
      integration,
    }) => {
      const crowdsec = await harness.standIn({ kind: 'crowdsec', api_key: KEY })
      await integration.goto('crowdsec')
      await integration.address('lapi').fill(crowdsec.url)
      await integration.field('lapi', 'api_key').fill(KEY)
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')

      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()

      await expect(integration.collectors).toHaveCount(2)
      await expect(integration.collectors).toContainText(['Connection check', 'Bans'])
      await expect(integration.collectorStates).toHaveText(['Working', 'Working'])
      await expect(integration.collectorTimings.nth(1)).toContainText('next run within a minute')
      await expect(integration.collectorErrors).toHaveCount(0)
      // Two of its five decisions are its own, one is a manual ban and one an import; the
      // community blocklist is left out. Seeing a ban again does not store it again, but each run
      // counts them.
      expect((await harness.rowCounts()).events).toBe(4)
      expect((await harness.rowCounts()).metric_samples).toBe(1)
      await harness.runCollectors()
      expect((await harness.rowCounts()).events).toBe(4)
      expect((await harness.rowCounts()).metric_samples).toBe(2)
    })
  })

  test.describe('the certificate a system presents', () => {
    test('is looked up and trusted before connecting, without choosing a way first', async ({
      harness,
      integration,
    }) => {
      const firewall = await harness.standIn({
        kind: 'opnsense',
        api_key: KEY,
        api_secret: SECRET,
        services: [],
      })
      await integration.goto('opnsense')
      await integration.address('api').fill(firewall.url)
      await integration.field('api', 'api_key').fill(KEY)
      await integration.field('api', 'api_secret').fill(SECRET)

      // The ways of checking are all still there, with the certificates this computer trusts
      // chosen, and the lookup does not need another to be.
      await expect(integration.tlsMode('api', 'system')).toBeChecked()
      await expect(integration.tlsMode('api', 'ca')).toBeVisible()
      await expect(integration.tlsMode('api', 'pinned')).toBeVisible()
      await integration.lookUp('api').click()

      await expect(integration.found('api')).toContainText('CN=fw.home.arpa')
      await expect(integration.foundFingerprint('api')).toHaveText(firewall.fingerprint ?? '')
      await expect(integration.selfSigned('api')).toBeVisible()
      await expect(integration.verdict('api')).toContainText('vouches for itself')
      // Nothing is saved yet, so there is nothing to test.
      await expect(integration.trustAndTest('api')).toHaveCount(0)

      await integration.trust('api').click()

      await expect(integration.trusted('api')).toBeVisible()
      await expect(integration.tlsMode('api', 'pinned')).toBeChecked()
      await expect(integration.fingerprint('api')).toHaveValue(firewall.fingerprint ?? '')
      await integration.save.click()
      await expect(integration.report).toContainText('The test passed')
      await expect(integration.status).toHaveText('Connected')
    })

    test('is reviewed and trusted in one step when a test fails over it', async ({
      harness,
      integration,
    }) => {
      const firewall = await harness.standIn({
        kind: 'opnsense',
        api_key: KEY,
        api_secret: SECRET,
        services: [],
      })
      await integration.goto('opnsense')
      await integration.address('api').fill(firewall.url)
      await integration.field('api', 'api_key').fill(KEY)
      await integration.field('api', 'api_secret').fill(SECRET)

      await integration.save.click()

      await expect(integration.report).toContainText('The test failed')
      await expect(integration.report).toContainText("The certificate isn't trusted")
      await expect(integration.status).toHaveText('Problem')
      // The failure offers what to do about it, where it is said.
      await expect(integration.reviewCertificate('api')).toBeVisible()
      await expect(integration.found('api')).toHaveCount(0)

      await integration.reviewFromReport().click()

      await expect(integration.found('api')).toBeVisible()
      await expect(integration.foundFingerprint('api')).toHaveText(firewall.fingerprint ?? '')
      await expect(integration.verdict('api')).toContainText('vouches for itself')
      await integration.trustAndTest('api').click()

      await expect(integration.report).toContainText('The test passed')
      await expect(integration.status).toHaveText('Connected')
      await expect(integration.trusted('api')).toBeVisible()
      await expect(integration.tlsMode('api', 'pinned')).toBeChecked()
      await expect(integration.reviewCertificate('api')).toHaveCount(0)
    })

    test('is reviewed from the card where it failed, and only trusted when told so', async ({
      harness,
      integration,
    }) => {
      const firewall = await harness.standIn({
        kind: 'opnsense',
        api_key: KEY,
        api_secret: SECRET,
        services: [],
      })
      await integration.goto('opnsense')
      await integration.address('api').fill(firewall.url)
      await integration.field('api', 'api_key').fill(KEY)
      await integration.field('api', 'api_secret').fill(SECRET)
      await integration.save.click()
      await expect(integration.status).toHaveText('Problem')

      await integration.reviewCertificate('api').click()
      await expect(integration.found('api')).toBeVisible()
      await integration.trust('api').click()

      // Trusting does not save by itself, and the page says so.
      await expect(integration.trusted('api')).toBeVisible()
      await expect(integration.unsaved).toBeVisible()
      await expect(integration.status).toHaveText('Problem')
      await integration.save.click()
      await expect(integration.report).toContainText('The test passed')
    })

    test('is trusted for each connection of Wazuh, which has two', async ({
      harness,
      integration,
    }) => {
      const wazuh = await harness.standIn({ kind: 'wazuh', username: USERNAME, password: PASSWORD })
      await integration.goto('wazuh')
      for (const connection of ['manager', 'indexer']) {
        await integration.address(connection).fill(wazuh.url)
        await integration.field(connection, 'username').fill(USERNAME)
        await integration.field(connection, 'password').fill(PASSWORD)
      }

      await integration.save.click()

      // Neither is trusted yet, and each says so with the way to trust it.
      await expect(integration.report).toContainText('The test failed')
      await expect(integration.checks).toHaveCount(2)
      await expect(integration.reviewCertificate('manager')).toBeVisible()
      await expect(integration.reviewCertificate('indexer')).toBeVisible()

      await integration.reviewFromReport('Manager API').click()
      await integration.trustAndTest('manager').click()
      // One is trusted, and the other still fails: it has a certificate setting of its own.
      await expect(integration.report).toContainText('The test failed')
      await expect(integration.reviewCertificate('manager')).toHaveCount(0)
      await expect(integration.reviewCertificate('indexer')).toBeVisible()

      await integration.reviewCertificate('indexer').click()
      await integration.trustAndTest('indexer').click()

      await expect(integration.report).toContainText('The test passed')
      await expect(integration.status).toHaveText('Connected')
    })

    test('that has changed since it was trusted fails the test, and the new one is reviewed and trusted', async ({
      harness,
      integration,
    }) => {
      await connectFirewall(harness, integration, [])
      const trusted = await integration.fingerprint('api').inputValue()
      // The system is now presenting another certificate than the one trusted (a fingerprint of
      // nothing but zeros).
      await integration.fingerprint('api').fill(trusted.replace(/[0-9a-f]/gi, '0'))

      await integration.save.click()

      await expect(integration.report).toContainText('The test failed')
      await expect(integration.report).toContainText('The certificate has changed')
      await expect(integration.status).toHaveText('Problem')
      await expect(integration.reviewCertificate('api')).toBeVisible()

      await integration.reviewFromReport().click()

      await expect(integration.verdict('api')).toContainText('The certificate has changed')
      await expect(integration.trusted('api')).toHaveCount(0)
      await integration.trustAndTest('api').click()

      await expect(integration.report).toContainText('The test passed')
      await expect(integration.fingerprint('api')).toHaveValue(trusted)
      await expect(integration.status).toHaveText('Connected')
    })

    test('says why an address cannot be looked at, and offers no certificate for it', async ({
      integration,
    }) => {
      await integration.goto('opnsense')
      await integration.address('api').fill('https://203.0.113.9')

      await integration.lookUp('api').click()

      await expect(integration.lookUpError('api')).toContainText("isn't a private network address")
      await expect(integration.found('api')).toHaveCount(0)
    })
  })

  test.describe('Wazuh', () => {
    test('says beside the certificate that its Let’s Encrypt page is for the dashboard only', async ({
      integration,
    }) => {
      await integration.goto('wazuh')

      await expect(integration.certificateNote('manager')).toContainText('dashboard only')
      await expect(integration.certificateNote('manager')).toContainText('self-signed')
      await expect(integration.certificateNote('indexer')).toContainText('root-ca.pem')

      // A product with nothing to add says nothing.
      await integration.goto('opnsense')
      await expect(integration.connection('api')).toBeVisible()
      await expect(integration.certificateNote('api')).toHaveCount(0)
    })

    test('reads its alerts from the indexer and its agents from the manager', async ({
      harness,
      integration,
    }) => {
      const wazuh = await harness.standIn({ kind: 'wazuh', username: USERNAME, password: PASSWORD })
      await integration.goto('wazuh')
      // At home the manager and the indexer are two servers; the stand-in answers as both.
      for (const connection of ['manager', 'indexer']) {
        await integration.address(connection).fill(wazuh.url)
        await integration.field(connection, 'username').fill(USERNAME)
        await integration.field(connection, 'password').fill(PASSWORD)
        // The certificate is looked up and trusted without choosing a way of checking first.
        await integration.lookUp(connection).click()
        await integration.trust(connection).click()
      }
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')

      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()

      await expect(integration.collectors).toHaveCount(4)
      await expect(integration.collectors).toContainText([
        'Connection check · Indexer',
        'Alerts · Indexer',
        'Connection check · Manager API',
        'Agents · Manager API',
      ])
      await expect(integration.collectorStates).toHaveText(new Array(4).fill('Working'))
      await expect(integration.collectorErrors).toHaveCount(0)
      // The four alerts of the last half hour and the agent that stopped, each stored once.
      expect((await harness.rowCounts()).events).toBe(5)
      // The agents in each of four states, counted on every run.
      expect((await harness.rowCounts()).metric_samples).toBe(4)
      await harness.runCollectors()
      expect((await harness.rowCounts()).events).toBe(5)
      expect((await harness.rowCounts()).metric_samples).toBe(8)
    })
  })

  /** Connects OPNsense to a stand-in with these services installed, pinning its certificate. */
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

    test('switches off the services that are installed but not running, until you switch them on', async ({
      harness,
      integration,
    }) => {
      await connectFirewall(harness, integration, ['suricata'], ['openvpn'])

      await expect(integration.report).toContainText(
        'Switched off, as they are installed but not running: OpenVPN.',
      )
      await expect(integration.module('api', 'OpenVPN')).toContainText('Stopped')
      await expect(integration.moduleSwitch('api', 'OpenVPN')).not.toBeChecked()
      await expect(integration.moduleSwitch('api', 'Suricata')).toBeChecked()
      await expect(integration.unsaved).toBeHidden()

      // It is the owner's to switch on, and a later test leaves it on.
      await integration.moduleSwitch('api', 'OpenVPN').check()
      await integration.save.click()
      await expect(integration.report).toContainText('The test passed')
      await expect(integration.report).not.toContainText('Switched off')
      await expect(integration.moduleSwitch('api', 'OpenVPN')).toBeChecked()
    })

    test('reads its firewall log and what it measures beside the connection check', async ({
      harness,
      integration,
    }) => {
      await connectFirewall(harness, integration, [])

      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()

      // Suricata, Dnsmasq and Kea aren't installed on this one, so it has no jobs for their
      // alerts and leases. The jobs are listed by name.
      await expect(integration.collectors).toHaveCount(7)
      await expect(integration.collectors).toContainText([
        'Connection check',
        'Devices (ARP table)',
        'Processor use',
        'Firewall log',
        'Gateways',
        'Interface traffic',
        'System health',
      ])
      await expect(integration.collectorStates).toHaveText(new Array(7).fill('Working'))
      await expect(integration.collectorTimings.nth(3)).toContainText('next run within a minute')
      await expect(integration.collectorErrors).toHaveCount(0)
      // The three lines in the firewall's log are kept once, however often they are read.
      expect((await harness.rowCounts()).events).toBe(3)
      // What it measures is read again each time: 14 numbers for two interfaces, 9 for its
      // health, 4 for its gateway and 1 for its processors.
      expect((await harness.rowCounts()).metric_samples).toBe(28)
      // The three devices in its ARP table, each with its address, however often it is read.
      expect((await harness.rowCounts()).devices).toBe(3)
      expect((await harness.rowCounts()).device_addresses).toBe(3)
      await harness.runCollectors()
      expect((await harness.rowCounts()).events).toBe(3)
      expect((await harness.rowCounts()).metric_samples).toBe(56)
      expect((await harness.rowCounts()).devices).toBe(3)
      expect((await harness.rowCounts()).device_addresses).toBe(3)
    })

    test('reads the alerts of Suricata as well when it is installed', async ({
      harness,
      integration,
    }) => {
      await connectFirewall(harness, integration, ['suricata'])

      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()

      await expect(integration.collectors).toHaveCount(8)
      await expect(integration.collectors.nth(6)).toContainText('Suricata alerts')
      await expect(integration.collectorStates).toHaveText(new Array(8).fill('Working'))
      await expect(integration.collectorErrors).toHaveCount(0)
      // Three lines of the firewall's log and two alerts, kept once however often they are read.
      expect((await harness.rowCounts()).events).toBe(5)
      await harness.runCollectors()
      expect((await harness.rowCounts()).events).toBe(5)
    })

    test('reads the bans and alerts of the CrowdSec plugin as well when it is installed', async ({
      harness,
      integration,
    }) => {
      await connectFirewall(harness, integration, ['crowdsec'])

      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()

      await expect(integration.collectors).toHaveCount(9)
      await expect(integration.collectors).toContainText([
        'Connection check',
        'Devices (ARP table)',
        'Processor use',
        'CrowdSec alerts (plugin)',
        'CrowdSec bans (plugin)',
        'Firewall log',
        'Gateways',
        'Interface traffic',
        'System health',
      ])
      await expect(integration.collectorStates).toHaveText(new Array(9).fill('Working'))
      await expect(integration.collectorErrors).toHaveCount(0)
      // Three lines of the firewall's log, two bans (not the one from the community blocklist or
      // the one that has run out) and two alerts, kept once however often they are read.
      expect((await harness.rowCounts()).events).toBe(7)
      await harness.runCollectors()
      expect((await harness.rowCounts()).events).toBe(7)
    })

    test('lists the devices that hold leases from its DHCP servers as well when they are installed', async ({
      harness,
      integration,
    }) => {
      await connectFirewall(harness, integration, ['dnsmasq', 'kea'])

      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()

      await expect(integration.collectors).toHaveCount(9)
      await expect(integration.collectors).toContainText([
        'Connection check',
        'Devices (ARP table)',
        'Processor use',
        'Devices (Dnsmasq leases)',
        'Firewall log',
        'Gateways',
        'Interface traffic',
        'Devices (Kea leases)',
        'System health',
      ])
      await expect(integration.collectorStates).toHaveText(new Array(9).fill('Working'))
      await expect(integration.collectorErrors).toHaveCount(0)
      // Three in the ARP table, a printer with a lease from Dnsmasq (and the laptop that is in
      // the table too) and a camera with one from Kea: five devices, however often they are
      // listed.
      expect((await harness.rowCounts()).devices).toBe(5)
      await harness.runCollectors()
      expect((await harness.rowCounts()).devices).toBe(5)
      expect((await harness.rowCounts()).device_addresses).toBe(5)
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

  test.describe('VirusTotal', () => {
    test('is for the internet, with its one address fixed and its terms said beside the access level', async ({
      page,
      integration,
      integrations,
    }) => {
      await integrations.goto()
      await expect(integrations.card('virustotal')).toContainText('Threat intelligence')
      await integrations.card('virustotal').click()

      await expect(page).toHaveURL('/integrations/virustotal')
      await expect(integration.title).toHaveText('VirusTotal')
      // Its address is the one VirusTotal has, and cannot be typed over.
      await expect(integration.address('api')).toHaveValue('https://www.virustotal.com')
      await expect(integration.address('api')).not.toBeEditable()
      await expect(integration.connection('api')).toContainText(
        'This service has one address, so AresGate only ever sends its key there.',
      )
      // Its certificate is one the public authorities vouch for, so there is none to look up.
      await expect(integration.lookUp('api')).toHaveCount(0)
      // The key is typed in, as a secret.
      await expect(integration.field('api', 'api_key')).toHaveAttribute('type', 'password')
      // The free public API is chosen, and its terms are said beside the choice. Choosing the
      // premium one does not take them away.
      await expect(integration.connection('api').getByLabel('Free public API')).toBeChecked()
      await expect(integration.connection('api').getByTestId('caution-tier')).toContainText(
        'must not be used in business workflows',
      )
      await integration.connection('api').getByLabel('Premium API').check()
      await expect(integration.connection('api').getByTestId('caution-tier')).toContainText(
        "Premium's limits depend on your plan",
      )
    })

    test('shows that a key is saved, and never shows the key', async ({ page, integration }) => {
      // What a saved connection looks like to the page: its address is kept, and its key is
      // only known to be set. The key itself is never sent back, so none is shown.
      await page.route('**/api/integrations/virustotal', async (route) => {
        const response = await route.fetch()
        const body = (await response.json()) as {
          status: string
          connections: { url: string | null; status: string; secrets_set: string[] }[]
        }
        body.status = 'connected'
        for (const connection of body.connections) {
          connection.url = 'https://www.virustotal.com'
          connection.status = 'connected'
          connection.secrets_set = ['api_key']
        }
        await route.fulfill({ status: response.status(), json: body })
      })

      await integration.goto('virustotal')

      await expect(integration.status).toHaveText('Connected')
      await expect(integration.field('api', 'api_key')).toHaveValue('')
      await expect(integration.field('api', 'api_key')).toHaveAttribute('placeholder', 'Saved')
    })
  })

  test.describe('AlienVault OTX', () => {
    test('is threat intelligence on the internet, with its one address fixed and a pace to choose', async ({
      page,
      integration,
      integrations,
    }) => {
      await integrations.goto()
      await expect(integrations.card('otx')).toContainText('Threat intelligence')
      await integrations.card('otx').click()

      await expect(page).toHaveURL('/integrations/otx')
      await expect(integration.title).toHaveText('AlienVault OTX')
      await expect(integration.address('api')).toHaveValue('https://otx.alienvault.com')
      await expect(integration.address('api')).not.toBeEditable()
      await expect(integration.field('api', 'api_key')).toHaveAttribute('type', 'password')
      // The balanced pace is chosen, and what it means is said beside the choice.
      await expect(integration.connection('api').getByLabel('Balanced')).toBeChecked()
      await expect(integration.connection('api').getByTestId('caution-pace')).toContainText(
        'OTX publishes no limit on requests',
      )
      await integration.connection('api').getByLabel('Gentle').check()
      await expect(integration.connection('api').getByLabel('Gentle')).toBeChecked()
    })
  })

  test.describe('GreyNoise', () => {
    test('is threat intelligence on the internet, with a key only when there is an account', async ({
      page,
      integration,
      integrations,
    }) => {
      await integrations.goto()
      await expect(integrations.card('greynoise')).toContainText('Threat intelligence')
      await integrations.card('greynoise').click()

      await expect(page).toHaveURL('/integrations/greynoise')
      await expect(integration.title).toHaveText('GreyNoise')
      await expect(integration.address('api')).toHaveValue('https://api.greynoise.io')
      await expect(integration.address('api')).not.toBeEditable()
      // An account with a key is chosen, with the free plan, and the limits are said beside it.
      await expect(
        integration.connection('api').getByLabel('An account with an API key'),
      ).toBeChecked()
      await expect(integration.connection('api').getByLabel('Free', { exact: true })).toBeChecked()
      await expect(integration.field('api', 'api_key')).toHaveAttribute('type', 'password')
      await expect(integration.connection('api').getByTestId('caution-access')).toContainText(
        '10 lookups a day without an account',
      )

      // With no account there is no plan to choose and no key to enter.
      await integration.connection('api').getByLabel('No account').check()
      await expect(integration.connection('api').getByLabel('Free', { exact: true })).toHaveCount(0)
      await expect(integration.field('api', 'api_key')).toHaveCount(0)

      await integration.connection('api').getByLabel('An account with an API key').check()
      await integration.connection('api').getByLabel('Standard, Advanced or Elite').check()
      await expect(
        integration.connection('api').getByLabel('Standard, Advanced or Elite'),
      ).toBeChecked()
      await expect(integration.field('api', 'api_key')).toHaveAttribute('type', 'password')
    })
  })

  test.describe('NIST NVD', () => {
    test('is threat intelligence on the internet, with a key only when one is sent', async ({
      page,
      integration,
      integrations,
    }) => {
      await integrations.goto()
      await expect(integrations.card('nvd')).toContainText('Threat intelligence')
      await integrations.card('nvd').click()

      await expect(page).toHaveURL('/integrations/nvd')
      await expect(integration.title).toHaveText('NIST NVD')
      await expect(integration.address('api')).toHaveValue('https://services.nvd.nist.gov')
      await expect(integration.address('api')).not.toBeEditable()
      // A key is asked with, and the limits are said beside the choice.
      await expect(integration.connection('api').getByLabel('Ask with an API key')).toBeChecked()
      await expect(integration.field('api', 'api_key')).toHaveAttribute('type', 'password')
      await expect(integration.connection('api').getByTestId('caution-access')).toContainText(
        '5 requests in 30 seconds',
      )

      // With no key there is none to enter.
      await integration.connection('api').getByLabel('Ask without a key').check()
      await expect(integration.field('api', 'api_key')).toHaveCount(0)

      await integration.connection('api').getByLabel('Ask with an API key').check()
      await expect(integration.field('api', 'api_key')).toHaveAttribute('type', 'password')
    })
  })

  test.describe('Fingerbank', () => {
    test('is device intelligence on the internet, with its one address fixed and a setting for incident devices', async ({
      page,
      integration,
      integrations,
    }) => {
      await integrations.goto()
      await expect(integrations.card('fingerbank')).toContainText('Device intelligence')
      await integrations.card('fingerbank').click()

      await expect(page).toHaveURL('/integrations/fingerbank')
      await expect(integration.title).toHaveText('Fingerbank')
      await expect(integration.address('api')).toHaveValue('https://api.fingerbank.org')
      await expect(integration.address('api')).not.toBeEditable()
      await expect(integration.field('api', 'api_key')).toHaveAttribute('type', 'password')
      // Only the owner's own devices are identified until they allow more, and what that sends is
      // said beside the choice.
      await expect(integration.connection('api').getByLabel('Only my own devices')).toBeChecked()
      await expect(
        integration.connection('api').getByTestId('caution-incident_devices'),
      ).toContainText('hardware address and nothing else')
      await integration.connection('api').getByLabel('Also devices in incidents').check()
      await expect(
        integration.connection('api').getByLabel('Also devices in incidents'),
      ).toBeChecked()
    })
  })

  test.describe('finding an integration', () => {
    test('narrows the list by what is typed, and says when nothing matches', async ({
      integrations,
    }) => {
      await integrations.goto()

      await integrations.search.fill('fingerbank')
      await expect(integrations.names).toHaveText(['Fingerbank'])

      await integrations.search.fill('flag each')
      await expect(integrations.names).toHaveText(['VirusTotal'])

      await integrations.search.fill('no such integration')
      await expect(integrations.none).toBeVisible()
      await expect(integrations.names).toHaveCount(0)

      await integrations.clear.click()
      await expect(integrations.names).toHaveCount(9)
      await expect(integrations.search).toHaveValue('')
    })

    test('narrows the list by kind, and the count of what is set up stays whole', async ({
      integrations,
    }) => {
      await integrations.goto()

      await integrations.kind('Threat intelligence').click()
      await expect(integrations.names).toHaveText([
        'VirusTotal',
        'AlienVault OTX',
        'GreyNoise',
        'NIST NVD',
      ])
      await integrations.kind('Device intelligence').click()
      await expect(integrations.names).toHaveText(['Fingerbank'])
      await expect(integrations.count).toHaveText('0 of 9 set up')

      await integrations.kind('All').click()
      await expect(integrations.names).toHaveCount(9)
    })
  })

  test.describe('a limit on VirusTotal', () => {
    test('holds a test as a notice that the connection is still set up, not as a failure', async ({
      page,
      integration,
    }) => {
      await page.route('**/api/integrations/virustotal', async (route) => {
        const response = await route.fetch()
        const body = (await response.json()) as {
          status: string
          connections: { url: string | null; status: string; secrets_set: string[] }[]
        }
        body.status = 'connected'
        for (const connection of body.connections) {
          connection.url = 'https://www.virustotal.com'
          connection.status = 'connected'
          connection.secrets_set = ['api_key']
        }
        await route.fulfill({ status: response.status(), json: body })
      })
      await page.route('**/api/integrations/virustotal/test', async (route) => {
        await route.fulfill({
          status: 429,
          headers: { 'Retry-After': '40' },
          json: {
            detail: 'The limits on this connection hold the test. Try again in 40 seconds.',
          },
        })
      })
      await integration.goto('virustotal')

      await integration.test.click()

      await expect(page.getByTestId('test-held')).toContainText(
        'Try again in 40 seconds. The connection is still set up.',
      )
      await expect(page.getByTestId('failure')).toHaveCount(0)
      await expect(integration.status).toHaveText('Connected')
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
