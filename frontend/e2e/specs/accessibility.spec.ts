import { expect, expectAccessible, test } from '../support'

// Both themes, since contrast is checked against the colors each one draws.
for (const theme of ['light', 'dark'] as const) {
  test.describe(`accessibility in the ${theme} theme`, () => {
    test('the overview has no WCAG 2.2 AA problems', async ({ page, overview, shell }) => {
      await overview.goto()
      await expect(overview.databaseStatus).toHaveText('Database: Connected')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the not-found page has no WCAG 2.2 AA problems', async ({ page, shell }) => {
      await page.goto('/no/such/page')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the theme menu has no WCAG 2.2 AA problems', async ({ page, overview, shell }) => {
      await overview.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await shell.themeToggle.click()
      await expect(page.getByTestId('theme-system')).toBeVisible()

      await expectAccessible(page)
    })
  })
}

test.describe('theme', () => {
  test('keeps the choice after a reload', async ({ page, overview, shell }) => {
    await overview.goto()
    await shell.chooseTheme('dark')
    await shell.expectTheme('dark')

    await page.reload()

    await shell.expectTheme('dark')
  })

  test('follows the browser when the choice is System', async ({ page, overview, shell }) => {
    await page.emulateMedia({ colorScheme: 'dark' })
    await overview.goto()
    await shell.chooseTheme('system')
    await shell.expectTheme('dark')

    await page.emulateMedia({ colorScheme: 'light' })

    await shell.expectTheme('light')
  })
})
