import { AppShell, expect, test } from '../support'

const FIREFOX_ON_WINDOWS =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0'
const SAFARI_ON_IPHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'

test.describe('sign-ins page', () => {
  test('lists this browser alone, marked, with nothing to sign out', async ({ signIns }) => {
    await signIns.goto()

    await expect(signIns.signIns).toHaveCount(1)
    await expect(signIns.names).toContainText('Chrome')
    await expect(signIns.thisBrowser).toHaveText('This browser')
    await expect(signIns.details).toContainText('Signed in')
    await expect(signIns.details).toContainText('Last active')
    await expect(signIns.endButtons).toHaveCount(0)
    await expect(signIns.endOthers).toHaveCount(0)
  })

  test('lists the other browsers, each with a button that names it', async ({
    signIns,
    signInElsewhere,
  }) => {
    await signInElsewhere(FIREFOX_ON_WINDOWS)
    await signInElsewhere(SAFARI_ON_IPHONE)

    await signIns.goto()

    await expect(signIns.signIns).toHaveCount(3)
    const firefox = signIns.signIns.filter({ hasText: 'Firefox on Windows' })
    const safari = signIns.signIns.filter({ hasText: 'Safari on iOS' })
    await expect(firefox.getByTestId('end-sign-in')).toHaveAccessibleName(
      'Sign out Firefox on Windows',
    )
    await expect(safari.getByTestId('end-sign-in')).toHaveAccessibleName('Sign out Safari on iOS')
    // A phone is drawn as a phone.
    await expect(safari.locator('.lucide-smartphone')).toHaveCount(1)
    await expect(firefox.locator('.lucide-monitor')).toHaveCount(1)
    await expect(signIns.thisBrowser).toHaveCount(1)
    await expect(signIns.endOthers).toBeVisible()
  })

  test('signs one browser out after asking, and that browser has to sign in again', async ({
    activity,
    signIns,
    signInElsewhere,
  }) => {
    const elsewhere = await signInElsewhere(FIREFOX_ON_WINDOWS)
    await elsewhere.goto('/')
    await expect(elsewhere).toHaveURL('/')
    await signIns.goto()

    await signIns.endButtons.click()
    await expect(signIns.confirmTitle).toHaveText('Sign out Firefox on Windows?')
    await signIns.confirm.click()

    await expect(signIns.notice).toHaveText('Firefox on Windows was signed out.')
    await expect(signIns.signIns).toHaveCount(1)
    await expect(signIns.endOthers).toHaveCount(0)
    await elsewhere.goto('/')
    await expect(elsewhere).toHaveURL('/sign-in')

    await activity.goto()
    await expect(activity.entries.first()).toContainText('Other sign-ins were ended')
  })

  test('leaves the browser signed in when the question is cancelled', async ({
    signIns,
    signInElsewhere,
  }) => {
    const elsewhere = await signInElsewhere(FIREFOX_ON_WINDOWS)
    await signIns.goto()

    await signIns.endButtons.click()
    await signIns.cancel.click()

    await expect(signIns.confirmTitle).toBeHidden()
    await expect(signIns.signIns).toHaveCount(2)
    await expect(signIns.notice).toHaveCount(0)
    await elsewhere.goto('/')
    await expect(elsewhere).toHaveURL('/')
  })

  test('signs every other browser out after asking, and says how many', async ({
    signIns,
    signInElsewhere,
  }) => {
    const first = await signInElsewhere(FIREFOX_ON_WINDOWS)
    const second = await signInElsewhere(SAFARI_ON_IPHONE)
    await signIns.goto()

    await signIns.endOthers.click()
    await expect(signIns.confirmTitle).toHaveText('Sign out everywhere else?')
    await signIns.confirm.click()

    await expect(signIns.notice).toHaveText('2 other sign-ins were ended.')
    await expect(signIns.signIns).toHaveCount(1)
    await expect(signIns.thisBrowser).toBeVisible()
    await expect(signIns.endOthers).toHaveCount(0)
    for (const other of [first, second]) {
      await other.goto('/')
      await expect(other).toHaveURL('/sign-in')
    }
  })

  test('says so when one browser is signed out already, and lists again', async ({
    signIns,
    signInElsewhere,
  }) => {
    const elsewhere = await signInElsewhere(FIREFOX_ON_WINDOWS)
    await signIns.goto()
    await expect(signIns.signIns).toHaveCount(2)
    await signIns.endButtons.click()
    // It signs itself out while the question is being asked.
    await elsewhere.goto('/')
    await new AppShell(elsewhere).signOutFromMenu()
    await expect(elsewhere).toHaveURL('/sign-in')

    await signIns.confirm.click()

    await expect(signIns.failure).toHaveText('That sign-in has already ended.')
    await expect(signIns.signIns).toHaveCount(1)
  })

  test('says why the list can’t be shown, and tries again', async ({ page, signIns }) => {
    let fail = true
    await page.route('**/api/auth/sessions', (route) => (fail ? route.abort() : route.continue()))
    await signIns.goto()
    await expect(signIns.loadError).toContainText("Can't reach AresGate.")

    fail = false
    await signIns.retry.click()

    await expect(signIns.loadError).toHaveCount(0)
    await expect(signIns.signIns).toHaveCount(1)
  })

  test('says so when AresGate can’t be reached to sign a browser out', async ({
    page,
    signIns,
    signInElsewhere,
  }) => {
    await signInElsewhere(FIREFOX_ON_WINDOWS)
    await page.route('**/api/auth/sessions/*/end', (route) => route.abort())
    await page.route('**/api/auth/sessions/end-others', (route) => route.abort())
    await signIns.goto()

    await signIns.endButtons.click()
    await signIns.confirm.click()
    await expect(signIns.failure).toContainText("Can't reach AresGate.")
    await expect(signIns.signIns).toHaveCount(2)

    await signIns.endOthers.click()
    await signIns.confirm.click()
    await expect(signIns.failure).toContainText("Can't reach AresGate.")
    await expect(signIns.signIns).toHaveCount(2)
  })
})
