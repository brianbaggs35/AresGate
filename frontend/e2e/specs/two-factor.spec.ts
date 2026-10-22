import { authenticatorCode, expect, test } from '../support'

test.describe('adding an authenticator app', () => {
  test('is off at first, and offers to add one', async ({ security }) => {
    await security.goto()

    await expect(security.twoFactorOff).toContainText('Off.')
    await expect(security.addApp).toBeVisible()
    await expect(security.twoFactorOn).toHaveCount(0)
  })

  test('shows a QR code and the key to type in, and turns on with a code from the app', async ({
    security,
  }) => {
    await security.goto()

    await security.addApp.click()

    await expect(security.qrCode).toBeVisible()
    await expect(security.openInApp).toHaveAttribute('href', /^otpauth:\/\/totp\/AresGate:/)
    await expect(security.key).toHaveText(/^([A-Z2-7]{4} ){7}[A-Z2-7]{4}$/)
    await expect(security.confirmCode).toBeFocused()

    const secret = ((await security.key.textContent()) ?? '').replaceAll(/\s/g, '')
    await security.confirmCode.fill(authenticatorCode(secret))
    await security.confirm.click()

    await expect(security.recoveryCodeItems).toHaveCount(10)
    await expect(security.codesDone).toBeDisabled()
    await security.codesSaved.check()
    await security.codesDone.click()
    await expect(security.twoFactorOn).toHaveText('On')
    await expect(security.recoveryCodesLeft).toHaveText('10 recovery codes left')
    await expect(security.recoveryCodeItems).toHaveCount(0)
  })

  test('says when the code is wrong, and lets another be tried', async ({ security }) => {
    await security.goto()
    await security.addApp.click()
    const secret = ((await security.key.textContent()) ?? '').replaceAll(/\s/g, '')

    await security.confirmCode.fill('000000')
    await security.confirm.click()

    await expect(security.twoFactorError).toContainText("That code isn't right")
    await expect(security.confirmCode).toHaveValue('')
    await security.confirmCode.fill(authenticatorCode(secret))
    await security.confirm.click()
    await expect(security.recoveryCodeItems).toHaveCount(10)
  })

  test('asks for the code before it asks the server', async ({ page, security }) => {
    await security.goto()
    await security.addApp.click()
    const requests: string[] = []
    page.on('request', (request) => requests.push(request.url()))

    await security.confirm.click()

    await expect(page.getByText('Enter the code from the app.')).toBeVisible()
    expect(requests.filter((url) => url.endsWith('/api/auth/two-factor/confirm'))).toEqual([])
  })

  test('can be given up on, and leaves it off', async ({ security }) => {
    await security.goto()
    await security.addApp.click()

    await security.cancel.click()

    await expect(security.twoFactorOff).toBeVisible()
    await expect(security.key).toHaveCount(0)
  })

  test('copies the recovery codes', async ({ context, page, security }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await security.goto()
    await security.addApp.click()
    const secret = ((await security.key.textContent()) ?? '').replaceAll(/\s/g, '')
    await security.confirmCode.fill(authenticatorCode(secret))
    await security.confirm.click()
    await expect(security.recoveryCodeItems).toHaveCount(10)
    const shown = (await security.recoveryCodeItems.allTextContents()).map((code) => code.trim())

    await security.copyCodes.click()

    await expect(security.copyNote).toHaveText('Copied.')
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(shown.join('\n'))
  })

  test('shows the new events in the activity list', async ({ security }) => {
    await security.goto()
    await security.addAuthenticator()

    await security.refresh.click()

    await expect(security.activities.first()).toContainText('Two-step verification was turned on')
  })

  test('says why it can’t tell whether it is on, and tries again', async ({ page, security }) => {
    let fail = true
    await page.route('**/api/auth/two-factor', (route) => (fail ? route.abort() : route.continue()))
    await security.goto()
    await expect(security.twoFactorLoadError).toContainText("Can't reach AresGate.")

    fail = false
    await security.twoFactorRetry.click()

    await expect(security.twoFactorLoadError).toHaveCount(0)
    await expect(security.twoFactorOff).toBeVisible()
  })
})

test.describe('signing in with an authenticator app', () => {
  test('asks for a code after the password, and signs in with the next code from the app', async ({
    page,
    security,
    shell,
    signIn,
    overview,
    baseline,
  }) => {
    await security.goto()
    const { secret } = await security.addAuthenticator()
    await shell.signOutFromMenu()

    await signIn.signIn(baseline.account)

    await expect(signIn.title).toHaveText('Enter a code')
    await expect(signIn.code).toBeFocused()
    await expect(page).toHaveURL('/sign-in')
    await signIn.enterCode(authenticatorCode(secret, 1))
    await expect(page).toHaveURL('/')
    await expect(overview.card).toBeVisible()
  })

  test('goes on to the page that was asked for', async ({
    page,
    security,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()
    const { secret } = await security.addAuthenticator()
    await shell.signOutFromMenu()
    await page.goto('/security')
    await expect(page).toHaveURL('/sign-in?next=/security')

    await signIn.signIn(baseline.account)
    await signIn.enterCode(authenticatorCode(secret, 1))

    await expect(page).toHaveURL('/security')
  })

  test('says when the code is wrong, and lets another be tried', async ({
    page,
    security,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()
    const { secret } = await security.addAuthenticator()
    await shell.signOutFromMenu()
    await signIn.signIn(baseline.account)

    await signIn.enterCode('000000')

    await expect(signIn.error).toHaveText("That code isn't right.")
    await expect(signIn.code).toHaveValue('')
    await signIn.enterCode(authenticatorCode(secret, 1))
    await expect(page).toHaveURL('/')
  })

  test('takes a recovery code in place of the app, once', async ({
    page,
    security,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()
    const { recoveryCodes } = await security.addAuthenticator()
    await shell.signOutFromMenu()
    await signIn.signIn(baseline.account)
    await signIn.enterCode(recoveryCodes[0] ?? '')
    await expect(page).toHaveURL('/')

    await security.goto()
    await expect(security.recoveryCodesLeft).toHaveText('9 recovery codes left')
    await shell.signOutFromMenu()
    await signIn.signIn(baseline.account)
    await signIn.enterCode(recoveryCodes[0] ?? '')

    await expect(signIn.error).toHaveText("That code isn't right.")
  })

  test('goes back to the password for a different account', async ({
    security,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()
    await security.addAuthenticator()
    await shell.signOutFromMenu()
    await signIn.signIn(baseline.account)
    await expect(signIn.title).toHaveText('Enter a code')

    await signIn.startOver.click()

    await expect(signIn.title).toHaveText('Sign in')
    await expect(signIn.password).toHaveValue('')
    await expect(signIn.username).toHaveValue(baseline.account.username)
  })

  test('locks after five wrong codes, even for the right one', async ({
    security,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()
    const { secret } = await security.addAuthenticator()
    await shell.signOutFromMenu()
    await signIn.signIn(baseline.account)
    for (let attempt = 0; attempt < 5; attempt++) {
      await signIn.enterCode('000000')
      await expect(signIn.error).toHaveText("That code isn't right.")
      await expect(signIn.code).toHaveValue('')
    }

    await signIn.enterCode(authenticatorCode(secret, 1))

    await expect(signIn.error).toHaveText('Too many attempts. Try again in 1 minute.')
  })
})

test.describe('changing it', () => {
  test('makes new recovery codes with a recovery code, which end the old ones', async ({
    security,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()
    const { recoveryCodes } = await security.addAuthenticator()
    await expect(security.recoveryCodesLeft).toHaveText('10 recovery codes left')

    await security.renewCodes.click()
    await security.renewCode.fill(recoveryCodes[0] ?? '')
    await security.renew.click()

    await expect(security.recoveryCodeItems).toHaveCount(10)
    const fresh = (await security.recoveryCodeItems.allTextContents()).map((code) => code.trim())
    expect(fresh).not.toContain(recoveryCodes[1])
    await security.codesSaved.check()
    await security.codesDone.click()
    await expect(security.recoveryCodesLeft).toHaveText('10 recovery codes left')
    await shell.signOutFromMenu()
    await signIn.signIn(baseline.account)
    await signIn.enterCode(recoveryCodes[1] ?? '')
    await expect(signIn.error).toHaveText("That code isn't right.")
  })

  test('refuses new recovery codes for a wrong code, and stays signed in', async ({ security }) => {
    await security.goto()
    await security.addAuthenticator()

    await security.renewCodes.click()
    await security.renewCode.fill('000000')
    await security.renew.click()

    await expect(security.twoFactorError).toHaveText("That isn't right.")
    await expect(security.renewCode).toHaveValue('')
    await security.cancel.click()
    await expect(security.twoFactorOn).toBeVisible()
    await expect(security.accountName).toBeVisible()
  })

  test('suggests new recovery codes when few are left', async ({
    page,
    security,
    shell,
    signIn,
    baseline,
  }) => {
    await security.goto()
    const { recoveryCodes } = await security.addAuthenticator()
    for (const code of recoveryCodes.slice(0, 8)) {
      await shell.signOutFromMenu()
      await signIn.signIn(baseline.account)
      await signIn.enterCode(code)
      await expect(page).toHaveURL('/')
    }

    await security.goto()

    await expect(security.recoveryCodesLeft).toHaveText('2 recovery codes left')
    await expect(security.recoveryCodesLow).toContainText('running low')
  })

  test('turns off with the password and a code, and then the password alone signs in', async ({
    page,
    security,
    shell,
    signIn,
    overview,
    baseline,
  }) => {
    await security.goto()
    const { recoveryCodes } = await security.addAuthenticator()

    await security.turnOff.click()
    await security.turnOffPassword.fill(baseline.account.password)
    await security.turnOffCode.fill(recoveryCodes[0] ?? '')
    await security.confirmTurnOff.click()

    await expect(security.twoFactorOff).toBeVisible()
    await security.refresh.click()
    await expect(security.activities.first()).toContainText('Two-step verification was turned off')
    await shell.signOutFromMenu()
    await signIn.signIn(baseline.account)
    await expect(page).toHaveURL('/')
    await expect(overview.card).toBeVisible()
  })

  test('stays on when the password is wrong', async ({ security, baseline }) => {
    await security.goto()
    const { recoveryCodes } = await security.addAuthenticator()

    await security.turnOff.click()
    await security.turnOffPassword.fill(`${baseline.account.password} but wrong`)
    await security.turnOffCode.fill(recoveryCodes[0] ?? '')
    await security.confirmTurnOff.click()

    await expect(security.twoFactorError).toHaveText("The password or the code isn't right.")
    await expect(security.turnOffPassword).toHaveValue('')
    await security.cancel.click()
    await expect(security.twoFactorOn).toBeVisible()
    await expect(security.recoveryCodesLeft).toHaveText('10 recovery codes left')
  })
})
