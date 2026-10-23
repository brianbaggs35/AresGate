import { expect, test } from '../support'

const NEW_PASSWORD = 'a different long phrase for tests'
const FIREFOX_ON_WINDOWS =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0'

test.describe('changing the password', () => {
  test('changes it, and then the new one signs in and the old one does not', async ({
    page,
    security,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()

    await security.changePasswordTo(baseline.account.password, NEW_PASSWORD)

    await expect(security.passwordChanged).toHaveText('Your password was changed.')
    // What was typed is not left in the fields.
    await expect(security.currentPassword).toHaveValue('')
    await expect(security.newPassword).toHaveValue('')
    await expect(security.confirmNewPassword).toHaveValue('')

    await shell.signOutFromMenu()
    await signIn.signIn(baseline.account)
    await expect(signIn.error).toBeVisible()
    await signIn.signIn({ ...baseline.account, password: NEW_PASSWORD })
    await expect(page).toHaveURL('/')
  })

  test('signs out every other browser, and says how many', async ({
    page,
    security,
    signInElsewhere,
    baseline,
  }) => {
    const elsewhere = await signInElsewhere(FIREFOX_ON_WINDOWS)
    await elsewhere.goto('/')
    await expect(elsewhere).toHaveURL('/')
    await security.goto()

    await security.changePasswordTo(baseline.account.password, NEW_PASSWORD)

    await expect(security.passwordChanged).toHaveText(
      'Your password was changed, and 1 other sign-in was ended.',
    )
    // This browser stays signed in ...
    await page.reload()
    await expect(security.accountName).toHaveText(baseline.account.username)
    // ... and the other one has to sign in again.
    await elsewhere.goto('/')
    await expect(elsewhere).toHaveURL('/sign-in')
  })

  test('is recorded in the activity', async ({ security, activity, baseline }) => {
    await security.goto()
    await security.changePasswordTo(baseline.account.password, NEW_PASSWORD)
    await expect(security.passwordChanged).toBeVisible()

    await activity.goto()

    await expect(activity.entries.first()).toContainText('The password was changed')
  })

  test('asks for what is missing before asking the server', async ({ page, security }) => {
    let asked = false
    await page.route('**/api/auth/password', (route) => {
      asked = true
      return route.continue()
    })
    await security.goto()

    await security.changePassword.click()

    await expect(security.passwordCard).toContainText('Enter your current password.')
    await expect(security.passwordCard).toContainText('Use 12 to 128 characters.')
    await expect(security.currentPassword).toBeFocused()
    expect(asked).toBe(false)
  })

  test('says when the two new passwords differ', async ({ security, baseline }) => {
    await security.goto()
    await security.currentPassword.fill(baseline.account.password)
    await security.newPassword.fill(NEW_PASSWORD)
    await security.confirmNewPassword.fill('something else entirely')

    await security.changePassword.click()

    await expect(security.passwordCard).toContainText("The passwords don't match.")
    await expect(security.passwordChanged).toHaveCount(0)
  })

  test('says when the current password is not right, and keeps what was typed', async ({
    security,
    baseline,
  }) => {
    await security.goto()

    await security.changePasswordTo('not the right password', NEW_PASSWORD)

    await expect(security.passwordCard).toContainText("The password isn't right.")
    await expect(security.newPassword).toHaveValue(NEW_PASSWORD)
    await expect(security.passwordChanged).toHaveCount(0)

    // Typing a different one takes the message away, and it can be tried again.
    await security.currentPassword.fill(baseline.account.password)
    await expect(security.passwordCard).not.toContainText("The password isn't right.")
    await security.changePassword.click()
    await expect(security.passwordChanged).toBeVisible()
  })

  test('says why a new password is not accepted', async ({ security, baseline }) => {
    await security.goto()

    await security.changePasswordTo(baseline.account.password, 'abcdefghijklmnop')

    await expect(security.passwordCard).toContainText('too easy to guess')
    await expect(security.passwordChanged).toHaveCount(0)
  })

  test('does not accept the password already in use', async ({ security, baseline }) => {
    await security.goto()

    await security.changePasswordTo(baseline.account.password, baseline.account.password)

    await expect(security.passwordCard).toContainText("Choose a password you aren't using now.")
  })

  test('says so when AresGate can’t be reached', async ({ page, security, baseline }) => {
    await page.route('**/api/auth/password', (route) => route.abort())
    await security.goto()

    await security.changePasswordTo(baseline.account.password, NEW_PASSWORD)

    await expect(security.passwordError).toContainText("Can't reach AresGate.")
    await expect(security.passwordChanged).toHaveCount(0)
  })
})
