import type { Page } from '@playwright/test'

import { connectFirewall, expect, test, waitForMotion } from '../support'

test.describe('layout on a phone', () => {
  test('the dashboard fits the screen without scrolling sideways', async ({ page, dashboard }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )

    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('the command palette fits the screen, with rows big enough to tap', async ({
    page,
    dashboard,
    shell,
  }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    await shell.searchButton.click()
    await expect(shell.palette).toBeVisible()
    await expect(shell.paletteRows.first()).toBeVisible()

    // The box grows into place as it opens, so what it measures is read once it has.
    await expect
      .poll(async () => (await shell.paletteRows.first().boundingBox())?.height)
      .toBeGreaterThanOrEqual(44)
    const card = await shell.palette.boundingBox()
    const viewport = page.viewportSize()
    expect(card?.x).toBeGreaterThanOrEqual(0)
    expect((card?.x ?? 0) + (card?.width ?? 0)).toBeLessThanOrEqual(viewport?.width ?? 0)
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      ),
    ).toBeLessThanOrEqual(0)
  })

  test('the incidents, and an incident, fit the screen without scrolling sideways', async ({
    page,
    harness,
    incidents,
    incident,
  }) => {
    await harness.createIncidents([
      {
        address: '93.184.216.34',
        severity: 'critical',
        programs: ['wazuh', 'opnsense', 'crowdsec'],
        signals: 8,
        ban: true,
        device_name: 'a-device-with-quite-a-long-name-on-the-network',
      },
    ])
    const overflow = () =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )

    await incidents.goto()
    await expect(incidents.cards).toHaveCount(1)
    expect(await overflow()).toBeLessThanOrEqual(0)

    await incidents.cards.first().click()
    await expect(incident.reasonsCard).toBeVisible()
    await expect(incident.signals.first()).toBeVisible()
    expect(await overflow()).toBeLessThanOrEqual(0)
  })

  test('the search, what it found and the ways to search fit the screen', async ({
    page,
    harness,
    incidents,
  }) => {
    await harness.createIncidents([
      {
        address: '93.184.216.34',
        severity: 'critical',
        programs: ['wazuh', 'opnsense', 'crowdsec', 'ntopng'],
        signals: 8,
      },
      { address: '8.8.8.8', severity: 'high', programs: ['wazuh'], signals: 3 },
    ])
    const overflow = () =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(2)
    await expect(incidents.facets).toBeVisible()
    expect(await overflow()).toBeLessThanOrEqual(0)

    await incidents.search('severity>=medium -source:ntopng address:93.184.216.0/24 "a phrase"')
    await expect(incidents.terms).toHaveCount(4)
    expect(await overflow()).toBeLessThanOrEqual(0)

    await incidents.searchHelp.click()
    await expect(incidents.searchPanel).toBeVisible()
    expect(await overflow()).toBeLessThanOrEqual(0)
    const box = await incidents.searchPanel.boundingBox()
    const screen = page.viewportSize()
    expect(box?.x).toBeGreaterThanOrEqual(0)
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(screen?.width ?? 0)

    // A search that is kept is in the list, and what is there to tap fits the screen.
    await incidents.saved.keep('A kept search')
    await expect(incidents.saved.rows).toHaveCount(1)
    expect(await overflow()).toBeLessThanOrEqual(0)

    // Every row to tap, and every term to take off, is as big as a thumb.
    for (const row of [
      ...(await incidents.saved.rows.all()),
      ...(await incidents.saved.forget.all()),
      ...(await incidents.saved.save.all()),
      ...(await page.getByTestId('search-example').all()),
    ]) {
      expect((await row.boundingBox())?.height).toBeGreaterThanOrEqual(44)
    }
    for (const chip of await incidents.terms.all()) {
      expect((await chip.boundingBox())?.height).toBeGreaterThanOrEqual(44)
    }
  })

  test('the row that changes many incidents fits the screen, with every button to tap as big as a thumb', async ({
    page,
    harness,
    incidents,
  }) => {
    await harness.createIncidents([
      { address: '93.184.216.34', severity: 'critical', signals: 8 },
      { address: '8.8.8.8', severity: 'high', signals: 3 },
      { address: '1.1.1.1', severity: 'medium', signals: 1 },
    ])
    const overflow = () =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(3)
    expect(await overflow()).toBeLessThanOrEqual(0)

    await incidents.picks.nth(0).click()
    await incidents.picks.nth(1).click()
    await expect(incidents.picked).toHaveText('2 selected')
    expect(await overflow()).toBeLessThanOrEqual(0)

    const screen = page.viewportSize()
    const bar = await incidents.bulk.boundingBox()
    expect(bar?.x).toBeGreaterThanOrEqual(0)
    expect((bar?.x ?? 0) + (bar?.width ?? 0)).toBeLessThanOrEqual(screen?.width ?? 0)
    for (const button of [
      incidents.bulkStatus,
      incidents.bulkVerdict('not_suspicious'),
      incidents.bulkVerdict('low_priority'),
      incidents.bulkVerdict('threat'),
      incidents.letGo,
      // The boxes are small, and the label around each is what a thumb hits.
      incidents.pickPage.locator('xpath=..'),
      page.getByTestId('incident-pick').first(),
    ]) {
      const box = await button.boundingBox()
      expect(box?.height).toBeGreaterThanOrEqual(44)
      expect(box?.width).toBeGreaterThanOrEqual(44)
    }

    // It stays in view as the list is scrolled, under the top bar.
    await page.mouse.wheel(0, 400)
    await expect(incidents.bulk).toBeInViewport()

    await incidents.bulkVerdict('threat').click()
    await expect(incidents.dialogLines.first()).toBeVisible()
    expect(await overflow()).toBeLessThanOrEqual(0)
  })

  test('an incident with verdicts fits the screen, and its three buttons stack', async ({
    page,
    harness,
    incidents,
    incident,
  }) => {
    await harness.createIncidents([
      {
        address: '93.184.216.34',
        severity: 'high',
        programs: ['wazuh', 'opnsense'],
        signals: 6,
        device_name: 'a-device-with-quite-a-long-name-on-the-network',
      },
    ])
    await harness.createVerdicts([
      {
        verdict: 'low_priority',
        source: 'wazuh',
        signature: 'ET SCAN Potential SSH Scan',
        note: 'a reason that is long enough to need more than one line on a phone, to see it wrap',
      },
    ])
    await incidents.goto()
    await incidents.cards.first().click()
    await expect(incident.applied).toHaveCount(1)

    const [low, threat] = await Promise.all([
      incident.give('low_priority').boundingBox(),
      incident.give('threat').boundingBox(),
    ])
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )

    // One below the other, each as wide as the card.
    expect(threat?.y).toBeGreaterThan(low?.y ?? 0)
    expect(threat?.x).toBe(low?.x)
    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('the three verdicts on an incident card sit side by side within it', async ({
    harness,
    incidents,
  }) => {
    await harness.createIncidents([{ address: '93.184.216.34', signals: 3 }])
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(1)

    const [card, first, last] = await Promise.all([
      incidents.cards.first().boundingBox(),
      incidents.quick('not_suspicious').boundingBox(),
      incidents.quick('threat').boundingBox(),
    ])

    expect(last?.y).toBe(first?.y)
    expect(last?.x).toBeGreaterThan((first?.x ?? 0) + (first?.width ?? 0))
    expect((last?.x ?? 0) + (last?.width ?? 0)).toBeLessThanOrEqual(
      (card?.x ?? 0) + (card?.width ?? 0),
    )
    // Big enough to press with a thumb.
    expect(first?.height).toBeGreaterThanOrEqual(44)
  })

  test('puts the four numbers of an incident two to a row', async ({
    page,
    harness,
    incidents,
    incident,
  }) => {
    await harness.createIncidents([{ address: '93.184.216.34', signals: 3 }])
    await incidents.goto()
    await incidents.cards.first().click()
    await expect(incident.signalsTile).toBeVisible()
    // The page rises into place, and the boxes are only the same height once it has.
    await waitForMotion(page)

    const [first, second, third] = await Promise.all([
      incident.signalsTile.boundingBox(),
      incident.programsTile.boundingBox(),
      incident.addressesTile.boundingBox(),
    ])

    expect(first?.y).toBeCloseTo(second?.y ?? -1, 0)
    expect(third?.y).toBeGreaterThan((first?.y ?? 0) + (first?.height ?? 0) - 1)
  })

  test('the banner uses nearly the whole width', async ({ page, dashboard }) => {
    await dashboard.goto()

    const box = await dashboard.banner.boundingBox()
    const viewport = page.viewportSize()

    expect(box?.width).toBeGreaterThan((viewport?.width ?? 0) * 0.85)
  })

  test('puts the menu in a bar at the bottom, with no menu at the side', async ({
    page,
    shell,
    dashboard,
  }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    const bar = await shell.menu.boundingBox()
    const viewport = page.viewportSize()

    expect((bar?.y ?? 0) + (bar?.height ?? 0)).toBe(viewport?.height)
    expect(bar?.width).toBe(viewport?.width)
    await expect(shell.dashboardLink).toContainText('Dashboard')
    await expect(shell.menuWidthToggle).toHaveCount(0)
    await expect(page.locator('.v-navigation-drawer')).toHaveCount(0)
  })

  test('has the logo in the top bar, which goes home', async ({ page, shell, dashboard }) => {
    await page.goto('/no/such/page')
    await expect(shell.logo).toContainText('AresGate')
    await expect(shell.pageTitle).toHaveCount(0)

    await shell.logo.click()

    await expect(page).toHaveURL('/')
    await expect(dashboard.banner).toBeVisible()
  })

  test('keeps the end of a page clear of the bottom bar', async ({ shell, dashboard }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    const bar = await shell.menu.boundingBox()
    const room = await shell.main.evaluate((main) =>
      parseFloat(getComputedStyle(main).paddingBottom),
    )

    expect(room).toBeGreaterThanOrEqual(bar?.height ?? Infinity)
  })

  test('keeps the places that do not fit in the bar behind a More button', async ({
    page,
    shell,
    dashboard,
  }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()
    // The bar has room for four places and More, each wide enough to tap.
    for (const link of [
      shell.dashboardLink,
      shell.incidentsLink,
      shell.logsLink,
      shell.integrationsLink,
      shell.moreButton,
    ]) {
      expect((await link.boundingBox())?.width).toBeGreaterThanOrEqual(48)
    }
    await expect(shell.statusLink).toHaveCount(0)

    await shell.moreButton.click()

    await expect(shell.moreSheet).toBeVisible()
    await expect(shell.moreButton).toHaveAttribute('aria-expanded', 'true')
    await expect(shell.statusLink).toBeVisible()
    await expect(shell.settingsLink).toBeVisible()
    await shell.statusLink.click()
    await expect(page).toHaveURL('/status')
    await expect(shell.moreSheet).toBeHidden()
    await shell.expectCurrent('status')
    await expect(shell.moreButton).toHaveAttribute('aria-expanded', 'false')
  })

  test.describe('status', () => {
    test('the page fits the screen, with every place still reachable from the bottom bar', async ({
      page,
      shell,
      status,
    }) => {
      await status.goto()
      await expect(status.fine).toBeVisible()
      await expect(status.diagnostics).toBeVisible()

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow).toBeLessThanOrEqual(0)
      const viewport = page.viewportSize()
      const card = await status.aresgate.boundingBox()
      expect(card?.width).toBeGreaterThan((viewport?.width ?? 0) * 0.85)
      // Five places share the bar, each wide enough to tap.
      for (const link of [
        shell.dashboardLink,
        shell.incidentsLink,
        shell.logsLink,
        shell.integrationsLink,
        shell.moreButton,
      ]) {
        expect((await link.boundingBox())?.width).toBeGreaterThanOrEqual(48)
      }
    })

    test('puts a fact above its value, so long ones have the width', async ({ status }) => {
      await status.goto()
      await expect(status.aresgate).toBeVisible()

      const label = await status.aresgate.getByTestId('fact-label').first().boundingBox()
      const value = await status.fact('version').boundingBox()
      expect(value?.y).toBeGreaterThan((label?.y ?? 0) + (label?.height ?? 0) - 1)
    })
  })

  test.describe('integrations', () => {
    const overflow = (page: Page) =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )

    test('the list fits the screen, one card above the next', async ({ page, integrations }) => {
      await integrations.goto()
      await expect(integrations.names).toHaveCount(4)

      expect(await overflow(page)).toBeLessThanOrEqual(0)
      const first = await integrations.card('opnsense').boundingBox()
      const second = await integrations.card('ntopng').boundingBox()
      const viewport = page.viewportSize()
      expect(first?.width).toBeGreaterThan((viewport?.width ?? 0) * 0.85)
      expect(second?.y).toBeGreaterThan((first?.y ?? 0) + (first?.height ?? 0) - 1)
    })

    test('a page fits the screen, with a form, a certificate, the services and the log', async ({
      page,
      harness,
      integration,
    }) => {
      const firewall = await harness.standIn({
        kind: 'opnsense',
        api_key: 'a-key',
        api_secret: 'a-secret',
        services: ['suricata'],
      })
      await integration.goto('opnsense')
      await integration.address('api').fill(firewall.url)
      await integration.field('api', 'api_key').fill('a-key')
      await integration.field('api', 'api_secret').fill('a-secret')
      await integration.tlsMode('api', 'pinned').check()
      await integration.lookUp('api').click()
      await integration.trust('api').click()
      await integration.save.click()
      await expect(integration.module('api', 'Suricata')).toContainText('Running')
      await expect(integration.logCalls.first()).toBeVisible()
      await integration.useConnection('zenarmor').check()
      await expect(integration.address('zenarmor')).toBeVisible()

      expect(await overflow(page)).toBeLessThanOrEqual(0)
    })

    test('keeps the buttons and the end of the page clear of the bottom bar', async ({
      shell,
      integration,
    }) => {
      await integration.goto('crowdsec')
      await expect(integration.logEmpty).toBeVisible()

      await integration.logEmpty.scrollIntoViewIfNeeded()

      const bar = await shell.menu.boundingBox()
      const last = await integration.logEmpty.boundingBox()
      expect((last?.y ?? 0) + (last?.height ?? 0)).toBeLessThanOrEqual(bar?.y ?? 0)
    })
  })

  test.describe('before signing in', () => {
    test.use({ signedIn: false })

    test('the sign-in page fits the screen, with no menu', async ({ page, signIn }) => {
      await signIn.goto()
      await expect(signIn.submit).toBeVisible()

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )

      expect(overflow).toBeLessThanOrEqual(0)
      await expect(page.getByRole('navigation', { name: 'Main' })).toHaveCount(0)
    })

    test('the sign-in form uses nearly the whole width', async ({ page, signIn }) => {
      await signIn.goto()

      const box = await page.getByTestId('auth-card').boundingBox()
      const viewport = page.viewportSize()

      expect(box?.width).toBeGreaterThan((viewport?.width ?? 0) * 0.85)
    })

    test('setting up fits the screen', async ({ page, harness, setup, baseline }) => {
      await harness.loadFixture('fresh-install')
      await setup.goto()
      await setup.enterCode(baseline.fresh_install_setup_code)
      await expect(setup.createAccount).toBeVisible()

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )

      expect(overflow).toBeLessThanOrEqual(0)
    })
  })

  test('the settings pages fit the screen without scrolling sideways', async ({
    page,
    security,
    signIns,
    activity,
    verdicts,
    aiSettings,
    harness,
    data,
  }) => {
    await harness.createVerdicts([
      { verdict: 'not_suspicious', address: '93.184.216.34', note: 'a long reason '.repeat(8) },
    ])
    for (const [name, show, ready] of [
      ['account', () => security.goto(), security.twoFactorOff],
      ['sign-ins', () => signIns.goto(), signIns.thisBrowser],
      ['activity', () => activity.goto(), activity.entries.first()],
      ['verdicts', () => verdicts.goto(), verdicts.rows.first()],
      [
        'ai',
        async () => {
          await aiSettings.goto()
          await aiSettings.choose('ollama_cloud')
        },
        aiSettings.card('ollama_cloud'),
      ],
      ['data', () => data.goto(), data.eventsCard.getByTestId('retention-source').first()],
    ] as const) {
      await show()
      await expect(ready, name).toBeVisible()

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )

      expect(overflow, name).toBeLessThanOrEqual(0)
    }
  })

  test('draws a chart within the card, and keeps what a tap reads on the screen', async ({
    page,
    harness,
    integration,
    data,
  }) => {
    await connectFirewall(harness, integration, [])
    await harness.setWorker('running')
    await harness.runCollectors()
    await data.goto()
    const chart = data.eventsChart
    await expect(chart.getByTestId('bar-value')).toHaveText(['3'])

    const [card, drawing] = await Promise.all([
      data.eventsCard.boundingBox(),
      chart.getByRole('img').boundingBox(),
    ])
    expect((drawing?.x ?? 0) + (drawing?.width ?? 0)).toBeLessThanOrEqual(
      (card?.x ?? 0) + (card?.width ?? 0),
    )

    await chart.getByTestId('bar-slot').first().tap()
    await expect(chart.getByTestId('chart-tooltip')).toBeVisible()
    const tip = await chart.getByTestId('chart-tooltip').boundingBox()
    const viewport = page.viewportSize()?.width ?? 0
    expect(tip?.x ?? -1).toBeGreaterThanOrEqual(0)
    expect((tip?.x ?? 0) + (tip?.width ?? 0)).toBeLessThanOrEqual(viewport)

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('swipes through the incidents that need a decision, with the next one showing', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity({ collectors: ['ok'] })
    await harness.createIncidents([
      { address: '93.184.216.34', severity: 'critical', programs: ['wazuh'], minutes_ago: 10 },
      { address: '8.8.8.8', severity: 'high', programs: ['wazuh'], minutes_ago: 20 },
      { address: '1.1.1.1', severity: 'medium', programs: ['wazuh'], minutes_ago: 30 },
    ])

    await dashboard.goto()
    await expect(dashboard.needsYouCards).toHaveCount(3)

    const width = page.viewportSize()?.width ?? 0
    const [first, second] = await Promise.all([
      dashboard.needsYouCards.nth(0).boundingBox(),
      dashboard.needsYouCards.nth(1).boundingBox(),
    ])
    // The first starts where the page does, and the second is cut off by the edge of the screen.
    expect(first?.x ?? -1).toBeGreaterThanOrEqual(0)
    expect(first?.x ?? 99).toBeLessThanOrEqual(24)
    expect(second?.x ?? width).toBeLessThan(width - 16)
    expect((second?.x ?? 0) + (second?.width ?? 0)).toBeGreaterThan(width)
    // The row scrolls by itself, so the page does not.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)

    // The way to the others is a swipe, which snaps to the next card.
    await dashboard.needsYouCards.nth(2).scrollIntoViewIfNeeded()
    const third = await dashboard.needsYouCards.nth(2).boundingBox()
    expect(third?.x ?? -1).toBeGreaterThanOrEqual(0)
    expect((third?.x ?? 0) + (third?.width ?? 0)).toBeLessThanOrEqual(width)
  })

  test('keeps the buttons of the dashboard big enough for a finger', async ({
    harness,
    dashboard,
  }) => {
    await harness.createActivity({ collectors: ['ok'], traffic: { igc0: 80 } })
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    for (const button of [
      dashboard.day,
      dashboard.week,
      dashboard.refresh,
      dashboard.trafficChart.getByTestId('chart-view'),
    ]) {
      const box = await button.boundingBox()
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)
    }
  })

  test('lays the dashboard out in one column, with the numbers two to a row', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity({
      collectors: ['ok'],
      alerts: { critical: 1, high: 1, medium: 2, low: 1 },
      blocked: { '203.0.113.9': 5, '198.51.100.7': 2 },
      traffic: { igc0: 80, igc1: 5 },
      devices: 2,
    })
    await dashboard.goto()
    await expect(dashboard.alertRows).toHaveCount(5)

    const viewport = page.viewportSize()?.width ?? 0
    const [alerts, blocked, devices, banner, traffic, severity] = await Promise.all(
      [
        dashboard.alertsTile,
        dashboard.blockedTile,
        dashboard.devicesTile,
        dashboard.banner,
        dashboard.trafficCard,
        dashboard.alertsCard,
      ].map((item) => item.boundingBox()),
    )
    // The two are read a moment apart, so a hair of difference is the page settling.
    expect(alerts?.y).toBeCloseTo(blocked?.y ?? Number.NaN, 0)
    expect(alerts?.width).toBeLessThan(viewport / 2)
    expect(devices?.y).toBeGreaterThan(alerts?.y ?? 0)
    expect(banner?.width).toBeGreaterThan(viewport * 0.85)
    // The charts are under one another and each as wide as the page.
    expect(severity?.y).toBeGreaterThan((traffic?.y ?? 0) + (traffic?.height ?? 0))
    expect(traffic?.width).toBeGreaterThan(viewport * 0.85)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('keeps what a tap on the traffic chart reads on the screen', async ({
    page,
    harness,
    dashboard,
  }) => {
    await harness.createActivity({ collectors: ['ok'], traffic: { igc0: 80 } })
    await dashboard.goto()
    const chart = dashboard.trafficChart
    await chart.getByRole('img').scrollIntoViewIfNeeded()
    const plot = await chart.getByRole('img').boundingBox()
    const card = await dashboard.trafficCard.boundingBox()
    expect((plot?.x ?? 0) + (plot?.width ?? 0)).toBeLessThanOrEqual(
      (card?.x ?? 0) + (card?.width ?? 0),
    )

    await page.touchscreen.tap(
      (plot?.x ?? 0) + (plot?.width ?? 0) * 0.9,
      (plot?.y ?? 0) + (plot?.height ?? 0) / 2,
    )

    await expect(chart.getByTestId('chart-tooltip')).toBeVisible()
    const tip = await chart.getByTestId('chart-tooltip').boundingBox()
    const viewport = page.viewportSize()?.width ?? 0
    expect(tip?.x ?? -1).toBeGreaterThanOrEqual(0)
    expect((tip?.x ?? 0) + (tip?.width ?? 0)).toBeLessThanOrEqual(viewport)
  })

  test('lists the settings pages as tabs across the top, above the page', async ({
    security,
    settings,
  }) => {
    await security.goto()
    await expect(security.passwordCard).toBeVisible()

    await expect(settings.nav.locator('.v-tabs')).toHaveCount(1)
    const [account, signIns, activity, card] = await Promise.all([
      settings.accountLink.boundingBox(),
      settings.signInsLink.boundingBox(),
      settings.activityLink.boundingBox(),
      security.passwordCard.boundingBox(),
    ])
    // Side by side, and above the card.
    expect(signIns?.x).toBeGreaterThan(account?.x ?? 0)
    expect(activity?.x).toBeGreaterThan(signIns?.x ?? 0)
    expect(signIns?.y).toBe(account?.y)
    expect((account?.y ?? 0) + (account?.height ?? 0)).toBeLessThanOrEqual(card?.y ?? 0)
  })

  test('changes page with the tabs', async ({ page, security, settings, signIns }) => {
    await security.goto()

    await settings.signInsLink.click()

    await expect(page).toHaveURL('/settings/sign-ins')
    await expect(signIns.card).toBeVisible()
    await expect(settings.signInsLink).toHaveAttribute('aria-current', 'page')
  })

  test('keeps the settings buttons clear of the bottom bar', async ({
    shell,
    signIns,
    signInElsewhere,
  }) => {
    await signInElsewhere('Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Firefox/130.0')
    await signIns.goto()
    await expect(signIns.endOthers).toBeVisible()

    await signIns.endButtons.scrollIntoViewIfNeeded()

    const bar = await shell.menu.boundingBox()
    const button = await signIns.endButtons.boundingBox()
    expect((button?.y ?? 0) + (button?.height ?? 0)).toBeLessThanOrEqual(bar?.y ?? 0)
  })
})
