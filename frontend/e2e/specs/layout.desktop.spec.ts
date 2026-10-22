import { expect, test } from '../support'

const MENU = { full: 264, rail: 72 }

test.describe('layout on a computer', () => {
  test('the overview stays a readable column on a wide screen', async ({ overview }) => {
    await overview.goto()

    const box = await overview.card.boundingBox()

    expect(box?.width).toBeLessThanOrEqual(720)
  })

  test('shows the menu at the side, with names, and the logo above it', async ({
    shell,
    overview,
  }) => {
    await overview.goto()

    await shell.expectMenuWidth('full')
    expect((await shell.menu.boundingBox())?.width).toBe(MENU.full)
    await expect(shell.overviewLink).toContainText('Overview')
    await expect(shell.logo).toContainText('AresGate')
    await expect(shell.pageTitle).toHaveText('Overview')
  })

  test('collapses the menu to icons, and opens it again', async ({ shell, overview }) => {
    await overview.goto()

    await shell.menuWidthToggle.click()

    await shell.expectMenuWidth('rail')
    await expect.poll(async () => (await shell.menu.boundingBox())?.width).toBe(MENU.rail)
    await expect(shell.overviewLink.getByText('Overview')).toBeHidden()
    // The names are still there for a screen reader, and the logo's link keeps its name.
    await expect(shell.overviewLink).toHaveAccessibleName('Overview')
    await expect(shell.logo).toBeVisible()

    await shell.menuWidthToggle.click()

    await shell.expectMenuWidth('full')
    await expect.poll(async () => (await shell.menu.boundingBox())?.width).toBe(MENU.full)
  })

  test('remembers how wide the menu was after a reload', async ({ page, shell, overview }) => {
    await overview.goto()
    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('rail')

    await page.reload()

    await shell.expectMenuWidth('rail')
  })

  test('names a place in the icons-only menu when it is hovered', async ({ shell, overview }) => {
    await overview.goto()
    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('rail')

    await shell.overviewLink.hover()

    await expect(shell.menuTooltip).toHaveText('Overview')
  })

  test('keeps the page clear of the menu, whatever its width', async ({ shell, overview }) => {
    await overview.goto()
    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('rail')

    const menu = await shell.menu.boundingBox()
    const card = await overview.card.boundingBox()

    expect(card?.x).toBeGreaterThanOrEqual((menu?.x ?? 0) + (menu?.width ?? 0))
  })
})

test.describe('layout on a tablet', () => {
  test.use({ viewport: { width: 768, height: 1024 } })

  test('starts with the menu as icons, to leave the page room', async ({ shell, overview }) => {
    await overview.goto()

    await shell.expectMenuWidth('rail')
    const menu = await shell.menu.boundingBox()
    const card = await overview.card.boundingBox()
    expect(card?.width).toBeGreaterThan(768 - MENU.rail - 48)
    expect(menu?.width).toBe(MENU.rail)
  })

  test('opens the menu, and remembers that', async ({ page, shell, overview }) => {
    await overview.goto()

    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('full')

    await page.reload()

    await shell.expectMenuWidth('full')
  })

  test('fits the screen without scrolling sideways', async ({ page, shell, overview }) => {
    await overview.goto()
    await shell.menuWidthToggle.click()
    await shell.expectMenuWidth('full')

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )

    expect(overflow).toBeLessThanOrEqual(0)
    expect((await overview.card.boundingBox())?.width).toBeGreaterThan(300)
  })
})
