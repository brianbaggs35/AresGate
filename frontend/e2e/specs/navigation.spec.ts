import { expect, test } from '../support'

test.describe('navigation', () => {
  test('shows a not-found page for an address the app does not have', async ({ page }) => {
    // The server hands every address to the app, so a refresh on any page works.
    const response = await page.goto('/no/such/page')

    expect(response?.ok()).toBe(true)
    await expect(page).toHaveTitle('Page not found · AresGate')
    await expect(page.getByTestId('not-found')).toContainText("That page doesn't exist.")
  })

  test('goes back to the overview from the not-found page', async ({ page, overview }) => {
    await page.goto('/no/such/page')

    await page.getByRole('link', { name: 'Back to the overview' }).click()

    await expect(page).toHaveURL('/')
    await expect(overview.card).toBeVisible()
  })

  test('goes home from the logo', async ({ page, shell, overview }) => {
    await page.goto('/no/such/page')

    await shell.logo.click()

    await expect(page).toHaveURL('/')
    await expect(overview.card).toBeVisible()
  })

  test('opens the overview from the menu', async ({ page, shell, overview }) => {
    await page.goto('/no/such/page')

    await shell.overviewLink.click()

    await expect(page).toHaveURL('/')
    await expect(page).toHaveTitle('Overview · AresGate')
    await expect(overview.card).toBeVisible()
  })

  test('marks the place the menu is on', async ({ page, shell }) => {
    await page.goto('/')
    await expect(shell.overviewLink).toHaveAttribute('aria-current', 'page')

    await page.goto('/no/such/page')

    await expect(shell.overviewLink).not.toHaveAttribute('aria-current', 'page')
  })

  test('lets the keyboard skip past the menu to the page', async ({ page, shell, overview }) => {
    await overview.goto()
    await expect(overview.card).toBeVisible()

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
