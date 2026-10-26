import { expect, test } from '../support'

const MENU = { full: 264, rail: 72 }

test.describe('layout on a computer', () => {
  test('the dashboard uses the room of a wide screen, up to a limit', async ({ dashboard }) => {
    await dashboard.goto()

    const box = await dashboard.banner.boundingBox()

    expect(box?.width).toBeGreaterThan(720)
    expect(box?.width).toBeLessThanOrEqual(1320)
  })

  test('the status page stays a readable column, with a fact beside its value', async ({
    status,
  }) => {
    await status.goto()
    await expect(status.aresgate).toBeVisible()

    const card = await status.aresgate.boundingBox()
    const label = await status.aresgate.getByTestId('fact-label').first().boundingBox()
    const value = await status.fact('version').boundingBox()

    expect(card?.width).toBeLessThanOrEqual(960)
    expect(value?.x).toBeGreaterThan((label?.x ?? 0) + (label?.width ?? 0) - 1)
  })

  test('shows the menu at the side, with names, and the logo above it', async ({
    shell,
    dashboard,
  }) => {
    await dashboard.goto()

    await shell.expectMenuWidth('full')
    expect((await shell.menu.boundingBox())?.width).toBe(MENU.full)
    await expect(shell.dashboardLink).toContainText('Dashboard')
    await expect(shell.logo).toContainText('AresGate')
    await expect(shell.pageTitle).toHaveText('Dashboard')
  })

  test('collapses the menu to icons, and opens it again', async ({ shell, dashboard }) => {
    await dashboard.goto()

    await shell.menuWidthToggle.click()

    await shell.expectMenuWidth('rail')
    await expect.poll(async () => (await shell.menu.boundingBox())?.width).toBe(MENU.rail)
    await expect(shell.dashboardLink.getByText('Dashboard')).toBeHidden()
    // The names are still there for a screen reader, and the logo's link keeps its name.
    await expect(shell.dashboardLink).toHaveAccessibleName('Dashboard')
    await expect(shell.logo).toBeVisible()

    await shell.menuWidthToggle.click()

    await shell.expectMenuWidth('full')
    await expect.poll(async () => (await shell.menu.boundingBox())?.width).toBe(MENU.full)
  })

  test('remembers how wide the menu was after a reload', async ({ page, shell, dashboard }) => {
    await dashboard.goto()
    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('rail')

    await page.reload()

    await shell.expectMenuWidth('rail')
  })

  test('names a place in the icons-only menu when it is hovered', async ({ shell, dashboard }) => {
    await dashboard.goto()
    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('rail')

    await shell.dashboardLink.hover()

    await expect(shell.menuTooltip).toHaveText('Dashboard')
  })

  test('keeps the page clear of the menu, whatever its width', async ({ shell, dashboard }) => {
    await dashboard.goto()
    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('rail')

    // The menu and the page glide to their new places together, so look until they have arrived.
    await expect
      .poll(async () => {
        const menu = await shell.menu.boundingBox()
        const card = await dashboard.banner.boundingBox()
        return (card?.x ?? 0) - ((menu?.x ?? 0) + (menu?.width ?? 0))
      })
      .toBeGreaterThanOrEqual(0)
  })

  test('lists the settings pages at the side of the page, not across the top', async ({
    security,
    settings,
  }) => {
    await security.goto()
    await expect(security.passwordCard).toBeVisible()

    await expect(settings.nav.locator('.v-tabs')).toHaveCount(0)
    const nav = await settings.nav.boundingBox()
    const card = await security.passwordCard.boundingBox()
    expect(nav?.x).toBeLessThan(card?.x ?? 0)
    expect((nav?.x ?? 0) + (nav?.width ?? 0)).toBeLessThanOrEqual(card?.x ?? 0)
    // The pages are listed one under another.
    const [first, second] = await Promise.all([
      settings.accountLink.boundingBox(),
      settings.signInsLink.boundingBox(),
    ])
    expect(second?.y).toBeGreaterThan(first?.y ?? 0)
  })
})

test.describe('layout on a tablet', () => {
  test.use({ viewport: { width: 768, height: 1024 } })

  test('starts with the menu as icons, to leave the page room', async ({ shell, dashboard }) => {
    await dashboard.goto()

    await shell.expectMenuWidth('rail')
    const menu = await shell.menu.boundingBox()
    const card = await dashboard.banner.boundingBox()
    expect(card?.width).toBeGreaterThan(768 - MENU.rail - 48)
    expect(menu?.width).toBe(MENU.rail)
  })

  test('opens the menu, and remembers that', async ({ page, shell, dashboard }) => {
    await dashboard.goto()

    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('full')

    await page.reload()

    await shell.expectMenuWidth('full')
  })

  test('fits the screen without scrolling sideways', async ({ page, shell, dashboard }) => {
    await dashboard.goto()
    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('full')

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )

    expect(overflow).toBeLessThanOrEqual(0)
    expect((await dashboard.banner.boundingBox())?.width).toBeGreaterThan(300)
  })

  test('puts the settings pages in tabs above the page, since the list would take its room', async ({
    page,
    security,
    settings,
  }) => {
    await security.goto()
    await expect(security.passwordCard).toBeVisible()

    await expect(settings.nav.locator('.v-tabs')).toHaveCount(1)
    const nav = await settings.nav.boundingBox()
    const card = await security.passwordCard.boundingBox()
    expect((nav?.y ?? 0) + (nav?.height ?? 0)).toBeLessThanOrEqual(card?.y ?? 0)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
})
