import { expect, test } from '../support'

const NEW_ACCOUNT = { username: 'first-admin', password: 'a long enough passphrase' }

test.describe('setting up a fresh install', () => {
  test.use({ signedIn: false })

  test.beforeEach(async ({ harness }) => {
    await harness.loadFixture('fresh-install')
  })

  test('sends everyone to the first step, wherever they go', async ({ page, setup }) => {
    await page.goto('/')
    await expect(page).toHaveURL('/setup')
    await expect(page).toHaveTitle('Set up · AresGate')
    await expect(setup.title).toHaveText('Set up AresGate')
    await expect(setup.step).toHaveText(/^Step 1 of 2/)

    await page.goto('/sign-in')
    await expect(page).toHaveURL('/setup')
  })

  test('says where to find the code', async ({ setup }) => {
    await setup.goto()

    await expect(setup.title.locator('..')).toContainText('make logs')
  })

  test('creates the account with the code, and signs in', async ({
    page,
    setup,
    overview,
    shell,
    baseline,
    harness,
  }) => {
    await setup.goto()

    await setup.enterCode(baseline.fresh_install_setup_code)
    await expect(setup.step).toHaveText(/^Step 2 of 2/)
    await setup.createAccountWith(NEW_ACCOUNT)

    await expect(page).toHaveURL('/')
    await expect(overview.card).toBeVisible()
    await expect(shell.userMenu).toHaveAccessibleName(`Account: ${NEW_ACCOUNT.username}`)
    expect((await harness.rowCounts()).users).toBe(1)
  })

  test('takes the code in lowercase, with spaces instead of dashes', async ({
    page,
    setup,
    baseline,
  }) => {
    await setup.goto()

    await setup.enterCode(baseline.fresh_install_setup_code.toLowerCase().replaceAll('-', ' '))
    await setup.createAccountWith(NEW_ACCOUNT)

    await expect(page).toHaveURL('/')
  })

  test('asks for twelve letters and numbers before moving on', async ({ setup }) => {
    await setup.goto()

    await setup.enterCode('K7QD-3MWX')

    await expect(setup.step).toHaveText(/^Step 1 of 2/)
    await expect(setup.code).toBeFocused()
    await expect(setup.title.locator('..')).toContainText('The code is 12 letters and numbers')
  })

  test('goes back to the code when the server says it is wrong', async ({ setup }) => {
    await setup.goto()
    await setup.enterCode('AAAA-AAAA-AAAA')

    await setup.createAccountWith(NEW_ACCOUNT)

    await expect(setup.step).toHaveText(/^Step 1 of 2/)
    await expect(setup.error).toHaveText("That setup code isn't right.")
    await expect(setup.code).toHaveValue('AAAA-AAAA-AAAA')
  })

  test('checks the account’s details before asking the server', async ({
    page,
    setup,
    baseline,
  }) => {
    await setup.goto()
    await setup.enterCode(baseline.fresh_install_setup_code)
    const requests: string[] = []
    page.on('request', (request) => requests.push(request.url()))

    await setup.createAccountWith({ username: 'x', password: 'short' }, 'different')

    await expect(page.getByText('Use 3 to 64 letters, numbers')).toBeVisible()
    await expect(page.getByText('Use 12 to 128 characters')).toBeVisible()
    await expect(page.getByText("The passwords don't match.")).toBeVisible()
    expect(requests.filter((url) => url.endsWith('/api/setup'))).toEqual([])
  })

  test('shows why the server refused a password, and lets the code be used again', async ({
    page,
    setup,
    baseline,
  }) => {
    await setup.goto()
    await setup.enterCode(baseline.fresh_install_setup_code)

    await setup.createAccountWith({ username: 'first-admin', password: 'passwordpassword' })

    await expect(setup.error).toContainText('too easy to guess')
    await expect(setup.step).toHaveText(/^Step 2 of 2/)
    await setup.password.fill(NEW_ACCOUNT.password)
    await setup.confirmation.fill(NEW_ACCOUNT.password)
    await setup.createAccount.click()
    await expect(page).toHaveURL('/')
  })

  test('goes back to the code, which is still there', async ({ setup, baseline }) => {
    await setup.goto()
    await setup.enterCode(baseline.fresh_install_setup_code)

    await setup.back.click()

    await expect(setup.step).toHaveText(/^Step 1 of 2/)
    await expect(setup.code).toHaveValue(baseline.fresh_install_setup_code)
  })

  test('can be done from the keyboard alone', async ({ page, setup, baseline }) => {
    await setup.goto()
    await expect(setup.code).toBeFocused()
    await page.keyboard.type(baseline.fresh_install_setup_code)
    await page.keyboard.press('Enter')
    await expect(setup.username).toBeFocused()

    await page.keyboard.type(NEW_ACCOUNT.username)
    await page.keyboard.press('Tab')
    await page.keyboard.type(NEW_ACCOUNT.password)
    // The button that shows the password is in the way.
    await page.keyboard.press('Tab')
    await page.keyboard.press('Tab')
    await page.keyboard.type(NEW_ACCOUNT.password)
    await page.keyboard.press('Enter')

    await expect(page).toHaveURL('/')
  })
})

test.describe('setting up an install that has an account', () => {
  test.use({ signedIn: false })

  test('goes to the sign-in page instead', async ({ page, setup, signIn }) => {
    await setup.goto()

    await expect(page).toHaveURL('/sign-in')
    await expect(signIn.title).toBeVisible()
  })
})
