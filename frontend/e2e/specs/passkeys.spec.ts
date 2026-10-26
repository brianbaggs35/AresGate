import { expect, test } from '../support'

// These run against a passkey device made of software (Chromium's virtual authenticator),
// which unlocks itself like a laptop with a fingerprint reader.

test.describe('adding a passkey', () => {
  test('starts with none, and offers to add one', async ({ security }) => {
    await security.goto()

    await expect(security.noPasskeys).toHaveText("You haven't added a passkey yet.")
    await expect(security.addPasskey).toBeVisible()
    await expect(security.passkeyNames).toHaveCount(0)
  })

  test('adds one under a name, and the device keeps the key', async ({
    security,
    authenticator,
    baseline,
  }) => {
    await security.goto()

    await security.addPasskey.click()
    await expect(security.newPasskeyName).toBeFocused()
    await expect(security.newPasskeyName).not.toHaveValue('')
    await security.newPasskeyName.fill('Test laptop')
    await security.passkeyPassword.fill(baseline.account.password)
    await security.createPasskey.click()

    await expect(security.passkeyNames).toHaveText(['Test laptop'])
    await expect(security.passkeyDetails).toContainText('Never used')
    await expect(security.passkeysCard.getByRole('heading', { name: 'Passkeys' })).toBeFocused()
    const held = await authenticator.passkeys()
    expect(held).toHaveLength(1)
    expect(held[0]).toMatchObject({ discoverable: true })
  })

  test('says when the password is wrong, and lets the right one be tried', async ({
    security,
    authenticator,
    baseline,
  }) => {
    await security.goto()
    await security.addPasskey.click()

    await security.passkeyPassword.fill('not the password')
    await security.createPasskey.click()

    await expect(security.passkeysError).toHaveText("The password isn't right.")
    await expect(security.passkeyPassword).toHaveValue('')
    expect(await authenticator.passkeys()).toHaveLength(0)
    await security.passkeyPassword.fill(baseline.account.password)
    await security.createPasskey.click()
    await expect(security.passkeyNames).toHaveCount(1)
  })

  test('asks for a name and the password before it asks the server', async ({ page, security }) => {
    await security.goto()
    await security.addPasskey.click()
    await security.newPasskeyName.fill('')
    const requests: string[] = []
    page.on('request', (request) => requests.push(request.url()))

    await security.createPasskey.click()

    await expect(page.getByText('Enter a name.')).toBeVisible()
    await expect(page.getByText('Enter your password.')).toBeVisible()
    expect(requests.filter((url) => url.includes('/api/auth/passkeys'))).toEqual([])
  })

  test('says when the device would not unlock, and adds nothing', async ({
    security,
    authenticator,
    baseline,
  }) => {
    await authenticator.setUnlockable(false)
    await security.goto()
    await security.addPasskey.click()

    await security.passkeyPassword.fill(baseline.account.password)
    await security.createPasskey.click()

    await expect(security.passkeysError).toContainText('Making the passkey was cancelled')
    await expect(security.newPasskeyName).toBeVisible()
    expect(await authenticator.passkeys()).toHaveLength(0)

    await authenticator.setUnlockable(true)
    await security.passkeyPassword.fill(baseline.account.password)
    await security.createPasskey.click()
    await expect(security.passkeyNames).toHaveCount(1)
  })

  test('can be given up on', async ({ security }) => {
    await security.goto()
    await security.addPasskey.click()

    await security.cancel.click()

    await expect(security.noPasskeys).toBeVisible()
    await expect(security.newPasskeyName).toHaveCount(0)
  })

  test('is recorded in the activity', async ({ security, activity, baseline }) => {
    await security.goto()
    await security.addPasskeyNamed('Test laptop', baseline.account.password)

    await activity.goto()

    await expect(activity.entries.first()).toContainText('A passkey was added')
  })
})

test.describe('removing a passkey', () => {
  test('forgets it, after the password', async ({ security, activity, baseline }) => {
    await security.goto()
    await security.addPasskeyNamed('Old phone', baseline.account.password)
    await expect(security.removePasskeyButtons).toHaveAccessibleName('Remove Old phone')

    await security.removePasskeyButtons.click()
    await expect(security.passkeyPassword).toBeFocused()
    await security.passkeyPassword.fill(baseline.account.password)
    await security.confirmRemovePasskey.click()

    await expect(security.noPasskeys).toBeVisible()
    await activity.goto()
    await expect(activity.entries.first()).toContainText('A passkey was removed')
  })

  test('says when the password is wrong, and keeps the passkey', async ({ security, baseline }) => {
    await security.goto()
    await security.addPasskeyNamed('Old phone', baseline.account.password)
    await security.removePasskeyButtons.click()

    await security.passkeyPassword.fill('not the password')
    await security.confirmRemovePasskey.click()

    await expect(security.passkeysError).toHaveText("The password isn't right.")
    await security.cancel.click()
    await expect(security.passkeyNames).toHaveText(['Old phone'])
  })
})

test.describe('signing in with a passkey', () => {
  test('needs nothing typed, and shows the dashboard', async ({
    page,
    security,
    shell,
    signIn,
    dashboard,
    baseline,
  }) => {
    await security.goto()
    await security.addPasskeyNamed('Test laptop', baseline.account.password)
    await shell.signOutFromMenu()
    await expect(page).toHaveURL('/sign-in')

    await signIn.passkey.click()

    await expect(page).toHaveURL('/')
    await expect(dashboard.banner).toBeVisible()
    await expect(shell.userMenu).toHaveAccessibleName(`Account: ${baseline.account.username}`)
  })

  test('goes on to the page that was asked for, and is noted as used', async ({
    page,
    security,
    activity,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()
    await security.addPasskeyNamed('Test laptop', baseline.account.password)
    await shell.signOutFromMenu()

    await signIn.goto('/sign-in?next=/settings/account')
    await signIn.passkey.click()

    await expect(page).toHaveURL('/settings/account')
    await expect(security.passkeyDetails).toContainText('Last used')
    await expect(security.passkeyDetails).not.toContainText('Never used')
    await activity.goto()
    await expect(activity.entries.first()).toContainText('Signed in')
  })

  test('goes straight in even when an authenticator app is on', async ({
    page,
    security,
    shell,
    signIn,
    dashboard,
    baseline,
  }) => {
    await security.goto()
    await security.addPasskeyNamed('Test laptop', baseline.account.password)
    await security.addAuthenticator()
    await shell.signOutFromMenu()

    await signIn.passkey.click()

    await expect(page).toHaveURL('/')
    await expect(dashboard.banner).toBeVisible()
  })

  test('says when AresGate no longer knows the passkey the device offers', async ({
    page,
    security,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()
    await security.addPasskeyNamed('Test laptop', baseline.account.password)
    await security.removePasskeyButtons.click()
    await security.passkeyPassword.fill(baseline.account.password)
    await security.confirmRemovePasskey.click()
    await expect(security.noPasskeys).toBeVisible()
    await shell.signOutFromMenu()

    await signIn.passkey.click()

    await expect(signIn.error).toHaveText("That passkey didn't work.")
    await expect(page).toHaveURL('/sign-in')
  })
})

test.describe('with nothing on the device to sign in with', () => {
  test.use({ signedIn: false })

  test('says the passkey was cancelled', async ({ page, signIn, authenticator }) => {
    expect(await authenticator.passkeys()).toHaveLength(0)
    await signIn.goto()

    await signIn.passkey.click()

    await expect(signIn.error).toContainText('Using the passkey was cancelled')
    await expect(page).toHaveURL('/sign-in')
  })
})

test.describe('in a browser without passkeys', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      Reflect.deleteProperty(window, 'PublicKeyCredential')
    })
  })

  test('the sign-in page does not offer one', async ({ page, security, shell, signIn }) => {
    await security.goto()
    await shell.signOutFromMenu()
    await expect(page).toHaveURL('/sign-in')

    await expect(signIn.submit).toBeVisible()
    await expect(signIn.passkey).toHaveCount(0)
  })

  test('the security page says so, and offers no way to add one', async ({ security }) => {
    await security.goto()

    await expect(security.passkeysUnsupported).toContainText("can't make a passkey")
    await expect(security.addPasskey).toHaveCount(0)
  })
})
