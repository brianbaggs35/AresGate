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
})
