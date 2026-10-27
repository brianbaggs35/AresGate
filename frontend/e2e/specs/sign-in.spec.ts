import { expect, test } from '../support'

test.describe('signing in', () => {
  test.use({ signedIn: false })

  test('asks for a sign-in before showing the app', async ({ page, signIn }) => {
    await page.goto('/')

    await expect(page).toHaveURL('/sign-in')
    await expect(page).toHaveTitle('Sign in · AresGate')
    await expect(signIn.title).toHaveText('Sign in')
    // Nothing of the app shows around it, not even the menu.
    await expect(page.getByRole('navigation', { name: 'Main' })).toHaveCount(0)
  })

  test('signs in with the account’s username and password, and shows the dashboard', async ({
    page,
    signIn,
    dashboard,
    shell,
    baseline,
  }) => {
    await signIn.goto()

    await signIn.signIn(baseline.account)

    await expect(page).toHaveURL('/')
    await expect(dashboard.banner).toBeVisible()
    await expect(shell.userMenu).toHaveAccessibleName(`Account: ${baseline.account.username}`)
  })

  test('ignores the case and spaces around the username', async ({ page, signIn, baseline }) => {
    await signIn.goto()

    await signIn.signIn({
      username: `  ${baseline.account.username.toUpperCase()} `,
      password: baseline.account.password,
    })

    await expect(page).toHaveURL('/')
  })

  test('goes on to the page that was asked for', async ({ page, signIn, security, baseline }) => {
    await page.goto('/settings/account')
    await expect(page).toHaveURL('/sign-in?next=/settings/account')

    await signIn.signIn(baseline.account)

    await expect(page).toHaveURL('/settings/account')
    await expect(security.accountName).toHaveText(baseline.account.username)
  })

  test('never goes on to another website', async ({ page, signIn, dashboard, baseline }) => {
    await signIn.goto('/sign-in?next=//example.com/phish')

    await signIn.signIn(baseline.account)

    await expect(page).toHaveURL('/')
    await expect(dashboard.banner).toBeVisible()
  })

  test('says so, and clears the password, when it is wrong', async ({ page, signIn, baseline }) => {
    await signIn.goto()

    await signIn.signIn({ ...baseline.account, password: 'not the right password' })

    await expect(signIn.error).toHaveText('Incorrect username or password.')
    await expect(signIn.password).toHaveValue('')
    await expect(signIn.username).toHaveValue(baseline.account.username)
    await expect(page).toHaveURL('/sign-in')
  })

  test('gives the same answer for a username that does not exist', async ({ signIn }) => {
    await signIn.goto()

    await signIn.signIn({ username: 'nobody-here', password: 'a long enough phrase' })

    await expect(signIn.error).toHaveText('Incorrect username or password.')
  })

  test('asks for both before it asks the server', async ({ page, signIn }) => {
    await signIn.goto()
    const requests: string[] = []
    page.on('request', (request) => requests.push(request.url()))

    await signIn.submit.click()

    await expect(page.getByText('Enter your username.')).toBeVisible()
    await expect(page.getByText('Enter your password.')).toBeVisible()
    expect(requests.filter((url) => url.endsWith('/api/auth/login'))).toEqual([])
  })

  test('locks the account after five wrong passwords, even for the right one', async ({
    signIn,
    baseline,
  }) => {
    await signIn.goto()
    for (let attempt = 0; attempt < 5; attempt++) {
      await signIn.signIn({ ...baseline.account, password: 'not the right password' })
      await expect(signIn.error).toHaveText('Incorrect username or password.')
    }

    await signIn.signIn(baseline.account)

    await expect(signIn.error).toContainText('Too many attempts. Try again in')
  })

  test('shows and hides the password that is typed', async ({ signIn }) => {
    await signIn.goto()
    await signIn.password.fill('a long enough phrase')
    await expect(signIn.password).toHaveAttribute('type', 'password')

    await signIn.showPassword.click()

    await expect(signIn.password).toHaveAttribute('type', 'text')
    await expect(signIn.showPassword).toHaveAttribute('aria-pressed', 'true')
  })

  test('can be done from the keyboard alone', async ({ page, signIn, baseline }) => {
    await signIn.goto()
    // The username has the focus already.
    await expect(signIn.username).toBeFocused()
    await page.keyboard.type(baseline.account.username)
    await page.keyboard.press('Tab')
    await page.keyboard.type(baseline.account.password)

    await page.keyboard.press('Enter')

    await expect(page).toHaveURL('/')
  })
})

test.describe('staying signed in', () => {
  test('keeps the sign-in over a reload', async ({ page, dashboard }) => {
    await dashboard.goto()
    await expect(dashboard.banner).toBeVisible()

    await page.reload()

    await expect(dashboard.banner).toBeVisible()
    await expect(page).toHaveURL('/')
  })

  test('leaves the sign-in page for someone who is signed in already', async ({
    page,
    signIn,
    dashboard,
  }) => {
    await signIn.goto()

    await expect(page).toHaveURL('/')
    await expect(dashboard.banner).toBeVisible()
  })

  test('says when the sign-in ended while the page was open, and goes back to where it was', async ({
    page,
    harness,
    shell,
    signIn,
    security,
    baseline,
    dashboard,
  }) => {
    await page.goto('/')
    // The dashboard has asked for what it shows, so nothing is on its way when the sign-in ends.
    await expect(dashboard.banner).toBeVisible()
    // Cleaning the database ends every sign-in, as the idle limit would.
    await harness.clean()

    await shell.goTo('settings')

    await expect(page).toHaveURL('/sign-in?next=/settings/account')
    await expect(signIn.endedNotice).toContainText('Your sign-in ended')
    await signIn.signIn(baseline.account)
    await expect(page).toHaveURL('/settings/account')
    await expect(security.accountName).toBeVisible()
  })
})

test.describe('signing out', () => {
  test('ends the sign-in from the account menu', async ({ page, shell, signIn }) => {
    await page.goto('/')

    await shell.signOutFromMenu()

    await expect(page).toHaveURL('/sign-in')
    await expect(signIn.title).toBeVisible()
    // The sign-in is really over: the app asks again.
    await page.goto('/settings/account')
    await expect(page).toHaveURL('/sign-in?next=/settings/account')
  })

  test('ends the sign-in from the account settings page', async ({ page, security, signIn }) => {
    await security.goto()

    await security.signOut.click()

    await expect(page).toHaveURL('/sign-in')
    await expect(signIn.title).toBeVisible()
  })

  test('says so when the account menu can’t sign out, and stays where it is', async ({
    page,
    shell,
  }) => {
    await page.route('**/api/auth/logout', (route) => route.abort())
    await page.goto('/')

    await shell.signOutFromMenu()

    await expect(shell.signOutError).toContainText("Can't reach AresGate.")
    await expect(page).toHaveURL('/')
  })

  test('says so when the account settings page can’t sign out, and stays where it is', async ({
    page,
    security,
  }) => {
    await page.route('**/api/auth/logout', (route) => route.abort())
    await security.goto()

    await security.signOut.click()

    await expect(security.signOutError).toContainText("Can't reach AresGate.")
    await expect(page).toHaveURL('/settings/account')
  })
})
