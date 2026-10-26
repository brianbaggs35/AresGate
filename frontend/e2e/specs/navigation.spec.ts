import { expect, test } from '../support'

test.describe('navigation', () => {
  test('shows a not-found page for an address the app does not have', async ({ page }) => {
    // The server hands every address to the app, so a refresh on any page works.
    const response = await page.goto('/no/such/page')

    expect(response?.ok()).toBe(true)
    await expect(page).toHaveTitle('Page not found · AresGate')
    await expect(page.getByTestId('not-found')).toContainText("That page doesn't exist.")
  })

  test('goes back to the dashboard from the not-found page', async ({ page, dashboard }) => {
    await page.goto('/no/such/page')

    await page.getByRole('link', { name: 'Back to the dashboard' }).click()

    await expect(page).toHaveURL('/')
    await expect(dashboard.banner).toBeVisible()
  })

  test('goes home from the logo', async ({ page, shell, dashboard }) => {
    await page.goto('/no/such/page')

    await shell.logo.click()

    await expect(page).toHaveURL('/')
    await expect(dashboard.banner).toBeVisible()
  })

  test('opens the dashboard from the menu', async ({ page, shell, dashboard }) => {
    await page.goto('/no/such/page')

    await shell.dashboardLink.click()

    await expect(page).toHaveURL('/')
    await expect(page).toHaveTitle('Dashboard · AresGate')
    await expect(dashboard.banner).toBeVisible()
  })

  test('marks the place the menu is on', async ({ page, shell }) => {
    await page.goto('/')
    await expect(shell.dashboardLink).toHaveAttribute('aria-current', 'page')

    await page.goto('/no/such/page')

    await expect(shell.dashboardLink).not.toHaveAttribute('aria-current', 'page')
  })

  test('lets the keyboard skip past the menu to the page', async ({ page, shell, dashboard }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    await page.keyboard.press('Tab')
    await expect(shell.skipLink).toBeFocused()
    // It appears on screen only while it has focus.
    const box = await shell.skipLink.boundingBox()
    expect(box?.y).toBeGreaterThanOrEqual(0)

    await page.keyboard.press('Enter')

    await expect(shell.main).toBeFocused()
    await expect(page).toHaveURL('/')
  })
})
