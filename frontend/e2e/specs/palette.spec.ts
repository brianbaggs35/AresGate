import { expect, test } from '../support'

test.describe('the command palette', () => {
  test('opens from the keyboard, finds a page by what it is called and goes there', async ({
    page,
    dashboard,
    shell,
  }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()
    await expect(shell.palette).toBeHidden()

    await shell.openPaletteWithKeys()
    await expect(shell.palette).toBeVisible()
    await expect(shell.paletteRows.first()).toBeVisible()

    await shell.chooseCommand('verdicts')

    await expect(page).toHaveURL('/settings/verdicts')
    await expect(shell.palette).toBeHidden()
  })

  test('closes with the same keys, and with Escape, and gives the keyboard back', async ({
    page,
    dashboard,
    shell,
  }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    await shell.openPaletteWithKeys()
    await page.keyboard.press('Control+K')
    await expect(shell.palette).toBeHidden()

    await shell.searchButton.focus()
    await page.keyboard.press('Enter')
    await expect(shell.palette).toBeVisible()
    await shell.waitForPaletteToSettle()
    await page.keyboard.press('Escape')
    await expect(shell.palette).toBeHidden()
    await expect(shell.searchButton).toBeFocused()
  })

  test('opens from its button, which a phone has no keys for', async ({ dashboard, shell }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    await shell.searchButton.click()

    await expect(shell.palette).toBeVisible()
    await expect(shell.paletteSearch).toBeFocused()
  })

  test('narrows as it is typed in, says how many it found and says when nothing matches', async ({
    dashboard,
    shell,
  }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()
    await shell.openPaletteWithKeys()
    await expect(shell.paletteCount).toHaveText(/^\d+ found$/)

    await shell.paletteSearch.fill('status')
    await expect(shell.paletteRows).toHaveText(['Status'])
    await expect(shell.paletteCount).toHaveText('1 found')

    await shell.paletteSearch.fill('zzzz')
    await expect(shell.paletteRows).toHaveCount(0)
    await expect(shell.paletteEmpty).toContainText('Nothing matches “zzzz”')
    await expect(shell.paletteCount).toHaveText('Nothing found')
  })

  test('is walked with the arrow keys, down from the field and back up to it', async ({
    page,
    dashboard,
    shell,
  }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()
    await shell.openPaletteWithKeys()

    await page.keyboard.press('ArrowDown')
    await expect(shell.paletteRows.nth(0)).toBeFocused()
    await page.keyboard.press('ArrowDown')
    await expect(shell.paletteRows.nth(1)).toBeFocused()
    await page.keyboard.press('ArrowUp')
    await expect(shell.paletteRows.nth(0)).toBeFocused()
    await page.keyboard.press('ArrowUp')
    await expect(shell.paletteSearch).toBeFocused()

    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL('/incidents')
  })

  test('looks for the incidents about an address that was typed whole', async ({
    page,
    harness,
    incidents,
    shell,
  }) => {
    await harness.createIncidents([
      { address: '93.184.216.34', severity: 'high', programs: ['wazuh', 'opnsense'], signals: 3 },
      { address: '8.8.8.8', severity: 'low', programs: ['wazuh'], status: 'resolved' },
    ])
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(1)
    await shell.openPaletteWithKeys()

    await shell.paletteSearch.fill('8.8.8.8')
    await expect(shell.paletteRows.first()).toHaveText('Find incidents about 8.8.8.8')
    await page.keyboard.press('Enter')

    await expect(page).toHaveURL('/incidents?view=all&q=8.8.8.8')
    await expect(incidents.cards).toHaveCount(1)
    await expect(incidents.cards.first()).toContainText('8.8.8.8')
  })

  test('changes the theme, and keeps it', async ({ page, dashboard, shell }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()
    await shell.openPaletteWithKeys()

    await shell.chooseCommand('dark theme')
    await shell.expectTheme('dark')
    await expect(shell.palette).toBeHidden()

    await page.reload()
    await shell.expectTheme('dark')
  })
})
