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

    test('the security page has no WCAG 2.2 AA problems', async ({ page, security, shell }) => {
      await security.goto()
      await expect(security.activities.first()).toBeVisible()
      await shell.chooseTheme(theme)
      await shell.expectTheme(theme)

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
