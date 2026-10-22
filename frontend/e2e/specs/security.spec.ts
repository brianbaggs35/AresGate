import { expect, test } from '../support'

test.describe('security page', () => {
  test('is in the menu, and says who is signed in', async ({ page, shell, security, baseline }) => {
    await page.goto('/')

    await shell.securityLink.click()

    await expect(page).toHaveURL('/security')
    await expect(page).toHaveTitle('Security · AresGate')
    await expect(shell.securityLink).toHaveAttribute('aria-current', 'page')
    await expect(security.accountName).toHaveText(baseline.account.username)
  })

  test('opens from the account menu too', async ({ page, shell }) => {
    await page.goto('/')

    await shell.userMenu.click()
    await page.getByTestId('user-security').click()

    await expect(page).toHaveURL('/security')
  })

  test('lists the sign-in that just happened, with where it was from', async ({
    security,
    baseline,
  }) => {
    await security.goto()

    await expect(security.activities.first()).toContainText(
      `Signed in · ${baseline.account.username}`,
    )
    await expect(security.activities.first()).toContainText('Chrome')
  })

  test('shows a wrong guess as a failure, newest first', async ({
    page,
    security,
    signIn,
    shell,
    baseline,
  }) => {
    await page.goto('/')
    await shell.signOutFromMenu()
    await signIn.signIn({ ...baseline.account, password: 'not the right password' })
    await expect(signIn.error).toBeVisible()
    await signIn.signIn(baseline.account)
    await expect(page).toHaveURL('/')

    await security.goto()

    await expect(security.activities.nth(0)).toContainText('Signed in')
    await expect(security.activities.nth(1)).toContainText('Sign-in failed')
    await expect(security.activities.nth(1).getByRole('img', { name: 'Failed' })).toBeVisible()
  })

  test('says why the activity can’t be listed, and tries again', async ({ page, security }) => {
    let fail = true
    await page.route('**/api/audit/events*', (route) => (fail ? route.abort() : route.continue()))
    await security.goto()
    await expect(security.activityError).toContainText("Can't reach AresGate.")

    fail = false
    await security.refresh.click()

    await expect(security.activityError).toHaveCount(0)
    await expect(security.activities.first()).toBeVisible()
  })
})
