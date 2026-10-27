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

    test('the table of logs and its View menu have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      logs,
      shell,
    }) => {
      await harness.createEvents([
        { summary: 'Blocked tcp', src_address: '203.0.113.7', dst_address: '192.168.1.20' },
        {
          kind: 'alert',
          severity: 'high',
          summary: 'ET SCAN',
          protocol: 'tcp',
          seconds_ago: 90_000,
        },
      ])
      await logs.goto()
      await expect(logs.rows).toHaveCount(2)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expect(logs.days).toHaveCount(2)
      await expectAccessible(page)

      await logs.view.click()
      await expect(logs.viewPanel).toBeVisible()
      await logs.columnBox('Protocol').check()
      await expectAccessible(page)
    })
  })
}
