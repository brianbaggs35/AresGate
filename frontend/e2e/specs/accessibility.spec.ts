import { authenticatorCode, expect, expectAccessible, test } from '../support'

// Both themes, since contrast is checked against the colors each one draws.
for (const theme of ['light', 'dark'] as const) {
  test.describe(`accessibility in the ${theme} theme`, () => {
    test('the overview has no WCAG 2.2 AA problems', async ({ page, overview, shell }) => {
      await overview.goto()
      await expect(overview.databaseStatus).toHaveText('Database: Connected')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the not-found page has no WCAG 2.2 AA problems', async ({ page, shell }) => {
      await page.goto('/no/such/page')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the account settings page has no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
    }) => {
      await security.goto()
      await expect(security.twoFactorOff).toBeVisible()
      await expect(security.noPasskeys).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the password card, with what is wrong and what came of it, has no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
      baseline,
    }) => {
      await security.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await security.changePassword.click()
      await expect(security.passwordCard).toContainText('Enter your current password.')
      await expectAccessible(page)

      await security.changePasswordTo('not the right password', 'a different long phrase for tests')
      await expect(security.passwordCard).toContainText("The password isn't right.")
      await expectAccessible(page)

      await security.currentPassword.fill(baseline.account.password)
      await security.changePassword.click()
      await expect(security.passwordChanged).toBeVisible()
      await expectAccessible(page)
    })

    test('the sign-ins page, and the questions it asks, have no WCAG 2.2 AA problems', async ({
      page,
      signIns,
      shell,
      signInElsewhere,
    }) => {
      await signInElsewhere('Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Firefox/130.0')
      await signIns.goto()
      await expect(signIns.signIns).toHaveCount(2)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await signIns.endButtons.click()
      await expect(signIns.confirmTitle).toBeVisible()
      await expectAccessible(page)
      await signIns.cancel.click()
      await expect(signIns.confirmTitle).toBeHidden()

      await signIns.endOthers.click()
      await expect(signIns.confirmTitle).toBeVisible()
      await expectAccessible(page)
      await signIns.confirm.click()
      await expect(signIns.notice).toBeVisible()
      await expectAccessible(page)
    })

    test('the data page, and its questions, have no WCAG 2.2 AA problems', async ({
      page,
      data,
      shell,
    }) => {
      await data.goto()
      await expect(data.eventsCard.getByTestId('retention-source')).toHaveCount(4)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await data.source(data.eventsCard, 'OPNsense').getByTestId('retention-change').click()
      await expect(data.dialogTitle).toBeVisible()
      await expectAccessible(page)

      await data.useDays.check()
      await data.days.fill('0')
      await data.save.click()
      await expect(data.dialog).toContainText('Enter a whole number of days')
      await expectAccessible(page)

      await data.days.fill('90')
      await data.save.click()
      await expect(data.eventsCard.getByTestId('retention-notice')).toBeVisible()
      await expectAccessible(page)
    })

    test('the status page, and its warning, have no WCAG 2.2 AA problems', async ({
      page,
      harness,
      integration,
      status,
      shell,
    }) => {
      await status.goto()
      await expect(status.fine).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      // A part with a problem turns the all clear into a warning, and its row into an error.
      const ntopng = await harness.standIn({ kind: 'ntopng', token: 'a-valid-ntopng-token' })
      await integration.goto('ntopng')
      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill('the wrong token')
      await integration.save.click()
      await expect(integration.status).toHaveText('Problem')
      // The collector worker and a collector with a problem are listed too.
      await harness.setWorker('running')
      await harness.runCollectors()
      await status.goto()
      await expect(status.attention).toBeVisible()
      await expect(status.collectorStates).toHaveText(['Working', ...new Array(4).fill('Problem')])
      await expectAccessible(page)

      await status.copy.click()
      await expect(status.copied.or(status.copyFailed)).toBeVisible()
      await expectAccessible(page)
    })

    test('the activity page has no WCAG 2.2 AA problems', async ({ page, activity, shell }) => {
      await activity.goto()
      await expect(activity.entries.first()).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('the passkeys card, adding one and removing one have no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
      authenticator,
      baseline,
    }) => {
      await security.goto()
      await expect(security.noPasskeys).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await security.addPasskey.click()
      await expect(security.newPasskeyName).toBeVisible()
      await expectAccessible(page)

      await security.passkeyPassword.fill('not the password')
      await security.createPasskey.click()
      await expect(security.passkeysError).toBeVisible()
      await expectAccessible(page)

      await security.passkeyPassword.fill(baseline.account.password)
      await security.createPasskey.click()
      await expect(security.passkeyNames).toHaveCount(1)
      expect(await authenticator.passkeys()).toHaveLength(1)
      await expectAccessible(page)

      await security.removePasskeyButtons.click()
      await expect(security.confirmRemovePasskey).toBeVisible()
      await expectAccessible(page)
    })

    test('adding an authenticator app has no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
    }) => {
      await security.goto()
      await expect(security.twoFactorOff).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await security.addApp.click()
      await expect(security.key).toBeVisible()
      await expectAccessible(page)

      await security.confirmCode.fill('000000')
      await security.confirm.click()
      await expect(security.twoFactorError).toBeVisible()
      await expectAccessible(page)
    })

    test('the recovery codes and the card when it is on have no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
    }) => {
      await security.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await security.addApp.click()
      const secret = ((await security.key.textContent()) ?? '').replaceAll(/\s/g, '')
      await security.confirmCode.fill(authenticatorCode(secret))
      await security.confirm.click()
      await expect(security.recoveryCodeItems).toHaveCount(10)
      await expectAccessible(page)

      await security.codesSaved.check()
      await security.codesDone.click()
      await expect(security.twoFactorOn).toBeVisible()
      await expectAccessible(page)
    })

    test('making new codes and turning it off have no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
    }) => {
      await security.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await security.addAuthenticator()

      await security.renewCodes.click()
      await expect(security.renewCode).toBeVisible()
      await expectAccessible(page)
      await security.cancel.click()

      await security.turnOff.click()
      await expect(security.turnOffPassword).toBeVisible()
      await expectAccessible(page)
    })

    test('the second step of signing in has no WCAG 2.2 AA problems', async ({
      page,
      security,
      shell,
      signIn,
      baseline,
    }) => {
      await security.goto()
      await security.addAuthenticator()
      await shell.signOutFromMenu()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await signIn.signIn(baseline.account)
      await expect(signIn.code).toBeVisible()
      await expectAccessible(page)

      await signIn.enterCode('000000')
      await expect(signIn.error).toBeVisible()
      await expectAccessible(page)
    })

    test('the account menu has no WCAG 2.2 AA problems', async ({ page, overview, shell }) => {
      await overview.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await shell.userMenu.click()
      await expect(shell.signOut).toBeVisible()

      await expectAccessible(page)
    })

    test.describe('before signing in', () => {
      test.use({ signedIn: false })

      test('the sign-in page has no WCAG 2.2 AA problems', async ({ page, signIn, shell }) => {
        await signIn.goto()
        await shell.chooseTheme(theme)
        await shell.expectTheme(theme)

        await expectAccessible(page)
      })

      test('the sign-in page with an error has no WCAG 2.2 AA problems', async ({
        page,
        signIn,
        shell,
        baseline,
      }) => {
        await signIn.goto()
        await shell.chooseTheme(theme)
        await shell.expectTheme(theme)
        await signIn.signIn({ ...baseline.account, password: 'not the right password' })
        await expect(signIn.error).toBeVisible()

        await expectAccessible(page)
      })

      test('both steps of setting up have no WCAG 2.2 AA problems', async ({
        page,
        harness,
        setup,
        shell,
        baseline,
      }) => {
        await harness.loadFixture('fresh-install')
        await setup.goto()
        await shell.chooseTheme(theme)
        await shell.expectTheme(theme)
        await expectAccessible(page)

        await setup.enterCode(baseline.fresh_install_setup_code)
        await expect(setup.step).toHaveText(/^Step 2 of 2/)
        await expectAccessible(page)

        await setup.createAccountWith({ username: 'x', password: 'short' }, 'different')
        await expect(page.getByText("The passwords don't match.")).toBeVisible()
        await expectAccessible(page)
      })
    })

    test('the theme menu has no WCAG 2.2 AA problems', async ({ page, overview, shell }) => {
      await overview.goto()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await shell.themeToggle.click()
      await expect(page.getByTestId('theme-system')).toBeVisible()

      await expectAccessible(page)
    })

    test('the integrations list has no WCAG 2.2 AA problems', async ({
      page,
      integrations,
      shell,
    }) => {
      await integrations.goto()
      await expect(integrations.names).toHaveCount(4)
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

      await expectAccessible(page)
    })

    test('an integration, with its mistakes and its log, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      integration,
      shell,
    }) => {
      const ntopng = await harness.standIn({ kind: 'ntopng', token: 'a-valid-token' })
      await integration.goto('ntopng')
      await expect(integration.title).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await expectAccessible(page)

      await integration.address('api').fill('http://8.8.8.8:3000')
      await integration.field('api', 'token').fill('a-token')
      await integration.save.click()
      await expect(integration.problems).toBeVisible()
      await expectAccessible(page)

      await integration.address('api').fill(ntopng.url)
      await integration.field('api', 'token').fill('the wrong token')
      await integration.save.click()
      await expect(integration.report).toContainText('The test failed')
      await expect(integration.logCalls).toHaveCount(1)
      await expectAccessible(page)

      await integration.field('api', 'token').fill('a-valid-token')
      await integration.save.click()
      await expect(integration.status).toHaveText('Connected')
      await expectAccessible(page)

      // The collection card, whether the worker has reported in or not, and with a job listed.
      await expect(integration.collectionWorker).toBeVisible()
      await expectAccessible(page)
      await harness.setWorker('running')
      await harness.runCollectors()
      await integration.collectionRefresh.click()
      await expect(integration.collectorStates).toHaveText(new Array(4).fill('Working'))
      await expectAccessible(page)

      await integration.disconnect.click()
      await expect(integration.confirmation).toBeVisible()
      await expectAccessible(page)
    })

    test('OPNsense, with its certificate, services and Zenarmor, has no WCAG 2.2 AA problems', async ({
      page,
      harness,
      integration,
      shell,
    }) => {
      const firewall = await harness.standIn({
        kind: 'opnsense',
        api_key: 'a-key',
        api_secret: 'a-secret',
        services: ['suricata', 'openvpn'],
      })
      await integration.goto('opnsense')
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)
      await integration.address('api').fill(firewall.url)
      await integration.field('api', 'api_key').fill('a-key')
      await integration.field('api', 'api_secret').fill('a-secret')
      await integration.tlsMode('api', 'pinned').check()
      await integration.lookUp('api').click()
      await expect(integration.found('api')).toBeVisible()
      await expectAccessible(page)

      await integration.trust('api').click()
      await integration.save.click()
      await expect(integration.module('api', 'Suricata')).toContainText('Running')
      await expectAccessible(page)

      await integration.useConnection('zenarmor').check()
      await expect(integration.address('zenarmor')).toBeVisible()
      await expectAccessible(page)
    })
  })
}

test.describe('theme', () => {
  test('keeps the choice after a reload', async ({ page, overview, shell }) => {
    await overview.goto()
    await shell.chooseTheme('dark')
    await shell.expectTheme('dark')

    await page.reload()

    await shell.expectTheme('dark')
  })

  test('still works when the browser will not store settings', async ({
    page,
    overview,
    shell,
  }) => {
    await page.addInitScript(() => {
      const refuse = () => {
        throw new DOMException('Storage is off', 'SecurityError')
      }
      Storage.prototype.getItem = refuse
      Storage.prototype.setItem = refuse
    })
    await page.emulateMedia({ colorScheme: 'light' })
    await overview.goto()
    await shell.expectTheme('light')

    await shell.chooseTheme('dark')

    await shell.expectTheme('dark')
  })

  test('follows the browser when the choice is System', async ({ page, overview, shell }) => {
    await page.emulateMedia({ colorScheme: 'dark' })
    await overview.goto()
    await shell.chooseTheme('system')
    await shell.expectTheme('dark')

    await page.emulateMedia({ colorScheme: 'light' })

    await shell.expectTheme('light')
  })
})
