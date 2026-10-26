import { expect, test } from '../support'

test.describe('starting up', () => {
  test('says when AresGate isn’t answering, and tries again', async ({
    page,
    shell,
    dashboard,
  }) => {
    let fail = true
    await page.route('**/api/setup/status', (route) => (fail ? route.abort() : route.continue()))
    await page.goto('/')
    await expect(shell.startupError).toContainText("Can't reach AresGate.")

    fail = false
    await shell.startupRetry.click()

    await expect(shell.startupError).toHaveCount(0)
    await expect(dashboard.banner).toBeVisible()
    await expect(page).toHaveURL('/')
  })
})
