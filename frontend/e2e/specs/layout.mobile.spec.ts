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
})
