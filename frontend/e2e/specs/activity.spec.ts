import { expect, test } from '../support'

test.describe('activity page', () => {
  test('lists the sign-in that just happened, with where it was from', async ({
    activity,
    baseline,
  }) => {
    await activity.goto()

    await expect(activity.entries.first()).toContainText(`Signed in · ${baseline.account.username}`)
    await expect(activity.entries.first()).toContainText('Chrome')
  })

  test('shows a wrong guess as a failure, newest first', async ({
    page,
    activity,
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

    await activity.goto()

    await expect(activity.entries.nth(0)).toContainText('Signed in')
    await expect(activity.entries.nth(1)).toContainText('Sign-in failed')
    await expect(activity.entries.nth(1).getByRole('img', { name: 'Failed' })).toBeVisible()
  })

  test('says why the activity can’t be listed, and tries again', async ({ page, activity }) => {
    let fail = true
    await page.route('**/api/audit/events*', (route) => (fail ? route.abort() : route.continue()))
    await activity.goto()
    await expect(activity.error).toContainText("Can't reach AresGate.")

    fail = false
    await activity.refresh.click()

    await expect(activity.error).toHaveCount(0)
    await expect(activity.entries.first()).toBeVisible()
  })

  test('sends you to sign in when the sign-in has ended', async ({ page, activity, harness }) => {
    await activity.goto()
    await expect(activity.entries.first()).toBeVisible()
    // Cleaning the database ends every sign-in, as the idle limit would.
    await harness.clean()

    await activity.refresh.click()

    await expect(page).toHaveURL('/sign-in?next=/settings/activity')
  })
})
