import type { Page } from '@playwright/test'

import { expect, test } from '../support'

test.describe('layout on a phone', () => {
  test('the overview fits the screen without scrolling sideways', async ({ page, overview }) => {
    await overview.goto()
    await expect(overview.databaseStatus).toHaveText('Database: Connected')

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )

    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('the status card uses nearly the whole width', async ({ page, overview }) => {
    await overview.goto()

    const box = await overview.card.boundingBox()
    const viewport = page.viewportSize()

    expect(box?.width).toBeGreaterThan((viewport?.width ?? 0) * 0.85)
  })

  test('puts the menu in a bar at the bottom, with no menu at the side', async ({
    page,
    shell,
    overview,
  }) => {
    await overview.goto()
    await expect(overview.databaseStatus).toHaveText('Database: Connected')

    const bar = await shell.menu.boundingBox()
    const viewport = page.viewportSize()

    expect((bar?.y ?? 0) + (bar?.height ?? 0)).toBe(viewport?.height)
    expect(bar?.width).toBe(viewport?.width)
    await expect(shell.overviewLink).toContainText('Overview')
    await expect(shell.menuWidthToggle).toHaveCount(0)
    await expect(page.locator('.v-navigation-drawer')).toHaveCount(0)
  })

  test('has the logo in the top bar, which goes home', async ({ page, shell, overview }) => {
    await page.goto('/no/such/page')
    await expect(shell.logo).toContainText('AresGate')
    await expect(shell.pageTitle).toHaveCount(0)

    await shell.logo.click()

    await expect(page).toHaveURL('/')
    await expect(overview.card).toBeVisible()
  })

  test('keeps the end of a page clear of the bottom bar', async ({ shell, overview }) => {
    await overview.goto()
    await expect(overview.card).toBeVisible()

    const bar = await shell.menu.boundingBox()
    const room = await shell.main.evaluate((main) =>
      parseFloat(getComputedStyle(main).paddingBottom),
    )

    expect(room).toBeGreaterThanOrEqual(bar?.height ?? Infinity)
  })

  test.describe('status', () => {
    test('the page fits the screen, with every place still in the bottom bar', async ({
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
      // Four places share the bar, each wide enough to tap.
      for (const link of [
        shell.overviewLink,
        shell.integrationsLink,
        shell.statusLink,
        shell.settingsLink,
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
  }) => {
    for (const [name, show, ready] of [
      ['account', () => security.goto(), security.twoFactorOff],
      ['sign-ins', () => signIns.goto(), signIns.thisBrowser],
      ['activity', () => activity.goto(), activity.entries.first()],
    ] as const) {
      await show()
      await expect(ready, name).toBeVisible()

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )

      expect(overflow, name).toBeLessThanOrEqual(0)
    }
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
