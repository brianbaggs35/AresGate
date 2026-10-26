import { expect, expectAccessible, test } from '../support'

// The icons-only menu only exists beside the page, so a phone never shows it.
for (const theme of ['light', 'dark'] as const) {
  test.describe(`accessibility of the side menu in the ${theme} theme`, () => {
    test('the icons-only menu has no WCAG 2.2 AA problems', async ({ page, dashboard, shell }) => {
      await dashboard.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await shell.menuWidthToggle.click()
      await shell.expectMenuWidth('rail')

      await expectAccessible(page)
    })

    test('a menu tooltip has no WCAG 2.2 AA problems', async ({ page, dashboard, shell }) => {
      await dashboard.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await shell.menuWidthToggle.click()
      await shell.expectMenuWidth('rail')
      await shell.dashboardLink.hover()
      await expect(shell.menuTooltip).toBeVisible()

      await expectAccessible(page)
    })
  })
}
