import { expect, test } from '../support'

const ID = '1234567890123456789'
const TOKEN = 'Zk3-_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_x'
const ADDRESS = `https://discord.com/api/webhooks/${ID}/${TOKEN}`
const OTHER_ID = '9876543210987654321'
const OTHER_TOKEN = 'Qq9-_zyxwvutsrqponmlkjihgfedcba9876543210ZYXWVUTSRQPONMLKJIHGFEDCBA-_y'
const OTHER_ADDRESS = `https://discord.com/api/webhooks/${OTHER_ID}/${OTHER_TOKEN}`

test.describe('alerts page', () => {
  test('is in the menu, and says nothing is set up on a new install', async ({
    page,
    shell,
    alerts,
  }) => {
    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('alerts')

    await expect(page).toHaveURL('/alerts')
    await expect(page).toHaveTitle('Alerts · AresGate')
    await shell.expectCurrent('alerts')
    await expect(alerts.heading).toHaveText('Alerts')
    await expect(alerts.empty).toContainText('No alerts are set up')
    await expect(alerts.list).toHaveCount(0)
  })

  test('adds a Discord channel, tests it, and never shows the address again', async ({
    harness,
    alerts,
    page,
  }) => {
    const discord = await harness.standIn({ kind: 'discord', webhook: `${ID}/${TOKEN}` })
    const answers: string[] = []
    page.on('response', async (response) => {
      if (response.url().includes('/api/')) answers.push(await response.text().catch(() => ''))
    })
    await alerts.goto()

    await alerts.emptyAdd.click()
    await expect(alerts.dialogTitle).toHaveText('Add a Discord destination')
    await expect(alerts.url).toHaveAttribute('type', 'password')
    await alerts.name.fill('Security channel')
    await alerts.url.fill(ADDRESS)
    await alerts.save.click()

    const card = alerts.destination('Security channel')
    await expect(alerts.notice).toContainText('Added Security channel.')
    await expect(card).toBeVisible()
    await expect(card.getByTestId('status')).toHaveText('Not tested yet')
    await expect(card.getByTestId('destination-address')).toContainText(
      'discord.com/api/webhooks/…6789/••••••••',
    )

    await card.getByTestId('destination-test').click()

    await expect(alerts.notice).toHaveText(
      'Test message sent to Security channel. Look for it in the channel.',
    )
    await expect(card.getByTestId('status')).toHaveText('Connected')
    await expect(card.getByTestId('destination-result')).toContainText('A message last got through')
    const [message] = await harness.standInRequests(discord.id)
    expect(message?.path).toBe(`/api/webhooks/${ID}/${TOKEN}`)
    expect(message?.user_agent).toMatch(/^DiscordBot \(/)
    expect(JSON.stringify(message?.body)).toContain('AresGate can reach this channel')
    expect(JSON.stringify(message?.body)).toContain('"allowed_mentions":{"parse":[]}')

    // The address went in once and has not come back in anything the page was told, or shown.
    await page.reload()
    await expect(card).toBeVisible()
    await expect(page.locator('body')).not.toContainText(TOKEN)
    expect(answers.join('\n')).not.toContain(TOKEN)
  })

  test('refuses an address that is not a Discord webhook, in words, and adds nothing', async ({
    alerts,
  }) => {
    await alerts.goto()
    await alerts.add.click()
    await alerts.name.fill('Somewhere')
    await alerts.url.fill('https://example.com/api/webhooks/1234567890123456789/abcdefghijklmnop')
    await alerts.save.click()

    await expect(alerts.dialog).toContainText("That isn't a Discord address.")
    await expect(alerts.dialog).toBeVisible()
    await alerts.url.fill('http://discord.com/api/webhooks/1234567890123456789/abcdefghijklmnop')
    await alerts.save.click()
    await expect(alerts.dialog).toContainText('A webhook address starts with https://.')
    await alerts.cancel.click()
    await expect(alerts.dialog).toHaveCount(0)
    await expect(alerts.empty).toBeVisible()
  })

  test('refuses a name that is taken, on the name', async ({ alerts }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await expect(alerts.destination('Security')).toBeVisible()

    await alerts.addDestination('security', OTHER_ADDRESS)

    await expect(alerts.dialog).toContainText("There's already a destination called security.")
    await alerts.cancel.click()
    await expect(alerts.destinations).toHaveCount(1)
  })

  test('says in words why a test did not get through, and what to do', async ({
    harness,
    alerts,
  }) => {
    await harness.standIn({ kind: 'discord', webhook: `${OTHER_ID}/${OTHER_TOKEN}` })
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    const card = alerts.destination('Security')

    await card.getByTestId('destination-test').click()

    await expect(card.getByTestId('status')).toHaveText('Problem')
    await expect(card.getByTestId('destination-error')).toContainText(
      "Discord doesn't accept this webhook (HTTP 404).",
    )
    await expect(card.getByTestId('destination-error')).toContainText('replace the address')
    await expect(alerts.notice).toHaveCount(0)
  })

  test('changes the name and keeps the address, or replaces the address', async ({
    harness,
    alerts,
    page,
  }) => {
    const discord = await harness.standIn({
      kind: 'discord',
      webhook: `${OTHER_ID}/${OTHER_TOKEN}`,
    })
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    const card = alerts.destination('Security')
    await card.getByTestId('destination-test').click()
    await expect(card.getByTestId('status')).toHaveText('Problem')

    // Renaming keeps the address, and how the last try went.
    await card.getByTestId('destination-edit').click()
    await expect(alerts.dialogTitle).toHaveText('Change this destination')
    await expect(alerts.name).toHaveValue('Security')
    await expect(alerts.url).toHaveValue('')
    await expect(alerts.dialog).toContainText('Saved. Leave this empty to keep it')
    await alerts.name.fill('Phone')
    await alerts.save.click()
    await expect(alerts.notice).toHaveText('Saved Phone.')
    const renamed = alerts.destination('Phone')
    await expect(renamed.getByTestId('status')).toHaveText('Problem')

    // A new address replaces the old and starts over, and then the test works.
    await renamed.getByTestId('destination-edit').click()
    await alerts.url.fill(OTHER_ADDRESS)
    await alerts.save.click()
    await expect(renamed.getByTestId('status')).toHaveText('Not tested yet')
    await expect(renamed.getByTestId('destination-address')).toContainText('…4321')
    await renamed.getByTestId('destination-test').click()
    await expect(renamed.getByTestId('status')).toHaveText('Connected')
    expect(await harness.standInRequests(discord.id)).toHaveLength(2)

    await page.reload()
    await expect(alerts.destination('Phone').getByTestId('status')).toHaveText('Connected')
  })

  test('turns a destination off and on, and keeps it across a visit', async ({ alerts, page }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    const card = alerts.destination('Security')
    const toggle = alerts.switchOf(card)
    await expect(toggle).toBeChecked()

    await toggle.click()

    await expect(alerts.notice).toHaveText('Security will not be sent anything.')
    await expect(card.getByTestId('destination-off')).toHaveText('Turned off')
    await page.reload()
    await expect(alerts.destination('Security').getByTestId('destination-off')).toBeVisible()
    await alerts.switchOf(alerts.destination('Security')).click()
    await expect(alerts.notice).toHaveText('Security will be sent alerts.')
    await expect(card.getByTestId('destination-off')).toHaveCount(0)
  })

  test('removes a destination after asking, and keeps it when that is cancelled', async ({
    alerts,
  }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await alerts.addDestination('Phone', OTHER_ADDRESS)
    await expect(alerts.destinations).toHaveCount(2)

    await alerts.destination('Security').getByTestId('destination-remove').click()
    await expect(alerts.confirmTitle).toHaveText('Remove this destination?')
    await alerts.confirmCancel.click()
    await expect(alerts.destinations).toHaveCount(2)

    await alerts.destination('Security').getByTestId('destination-remove').click()
    await alerts.confirm.click()

    await expect(alerts.notice).toHaveText('Removed Security.')
    await expect(alerts.destinations).toHaveCount(1)
    await expect(alerts.destination('Phone')).toBeVisible()
  })

  test('says it could not load, and loads when asked again', async ({ alerts, page }) => {
    await page.route('**/api/alerts/destinations', (route) => route.abort(), { times: 1 })

    await alerts.goto()

    await expect(alerts.error).toContainText("Can't reach AresGate.")
    await alerts.retry.click()
    await expect(alerts.empty).toBeVisible()
  })

  test('says why a change could not be made', async ({ alerts, page }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await page.route('**/api/alerts/destinations/*', (route) =>
      route.request().method() === 'PATCH' ? route.abort() : route.continue(),
    )

    await alerts.switchOf(alerts.destination('Security')).click()

    await expect(alerts.failure).toContainText("Can't reach AresGate.")
  })

  test('records what was done in the activity, without the address', async ({ alerts, page }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await expect(alerts.destination('Security')).toBeVisible()

    await page.goto('/settings/activity')

    await expect(page.getByText('An alert destination was added')).toBeVisible()
    await expect(page.locator('body')).not.toContainText(TOKEN)
  })
})
