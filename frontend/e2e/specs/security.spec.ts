import { expect, test } from '../support'

test.describe('settings area', () => {
  test('is in the menu, opens on the account page, and says who is signed in', async ({
    page,
    shell,
    settings,
    security,
    baseline,
  }) => {
    await page.goto('/')

    await shell.goTo('settings')

    await expect(page).toHaveURL('/settings/account')
    await expect(page).toHaveTitle('Settings · AresGate')
    await shell.expectCurrent('settings')
    await expect(settings.heading).toHaveText('Settings')
    await expect(security.accountName).toHaveText(baseline.account.username)
  })

  test('opens from the account menu too', async ({ page, shell }) => {
    await page.goto('/')

    await shell.userMenu.click()
    await page.getByTestId('user-settings').click()

    await expect(page).toHaveURL('/settings/account')
  })

  test('opens on the account page when only /settings is asked for', async ({ page, settings }) => {
    await settings.goto()

    await expect(page).toHaveURL('/settings/account')
  })

  test('still opens the account page from the old address of the Security page', async ({
    page,
    security,
  }) => {
    await page.goto('/security')

    await expect(page).toHaveURL('/settings/account')
    await expect(security.passwordCard).toBeVisible()
  })

  test('lists every page of the area, and marks the one that is open', async ({
    page,
    shell,
    settings,
    signIns,
    activity,
    security,
  }) => {
    await security.goto()
    await expect(settings.nav).toBeVisible()
    await expect(settings.accountLink).toHaveAttribute('aria-current', 'page')
    await expect(settings.signInsLink).not.toHaveAttribute('aria-current', 'page')

    await settings.signInsLink.click()
    await expect(page).toHaveURL('/settings/sign-ins')
    await expect(signIns.card).toBeVisible()
    await expect(settings.signInsLink).toHaveAttribute('aria-current', 'page')
    await expect(settings.accountLink).not.toHaveAttribute('aria-current', 'page')

    await settings.activityLink.click()
    await expect(page).toHaveURL('/settings/activity')
    await expect(activity.entries.first()).toBeVisible()
    await expect(settings.activityLink).toHaveAttribute('aria-current', 'page')

    await settings.accountLink.click()
    await expect(page).toHaveURL('/settings/account')
    await expect(security.passwordCard).toBeVisible()
    // Settings stays marked in the menu, whichever page of it is open.
    await shell.expectCurrent('settings')
  })

  test('keeps Settings marked in the menu on every page of the area', async ({
    shell,
    signIns,
    activity,
  }) => {
    await signIns.goto()
    await shell.expectCurrent('settings')

    await activity.goto()
    await shell.expectCurrent('settings')
  })

  test('asks for the cards in order: who, password, passkeys, two-step verification', async ({
    security,
  }) => {
    await security.goto()

    const cards = [security.passwordCard, security.passkeysCard, security.twoFactorCard]
    const tops = await Promise.all(cards.map(async (card) => (await card.boundingBox())?.y ?? 0))

    expect(tops).toEqual([...tops].sort((a, b) => a - b))
    await expect(security.accountName).toBeVisible()
  })
})
