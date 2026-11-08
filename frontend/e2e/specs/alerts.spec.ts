import type { IncidentRequest } from '../support'
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

  test.describe('what one is told', () => {
    test.beforeEach(async ({ harness }) => {
      // Four incidents going on: a critical and a high one, a medium one that was resolved,
      // and a low one.
      await harness.createIncidents([
        {
          address: '93.184.216.34',
          severity: 'critical',
          programs: ['wazuh', 'opnsense', 'crowdsec'],
          signals: 8,
          ban: true,
          minutes_ago: 4,
        },
        { address: '8.8.8.8', severity: 'high', programs: ['wazuh', 'opnsense'], signals: 3 },
        { address: '1.1.1.1', severity: 'medium', programs: ['ntopng'], status: 'resolved' },
        { address: '9.9.9.9', severity: 'low', programs: ['opnsense'] },
      ])
    })

    test('starts with what is serious and sure, and shows the card in words', async ({
      alerts,
    }) => {
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      const card = alerts.destination('Security')

      await expect(card.getByTestId('destination-rules')).toContainText(
        'Tells you about incidents that are medium or worse, when AresGate is at least 65% sure.',
      )
      await alerts.openRules('Security')

      await expect(alerts.rulesTitle).toHaveText('What Security is told')
      await expect(alerts.severity).toContainText('Medium or worse')
      await expect(alerts.confidence).toContainText('High: 65% or more')
      await expect(alerts.rulesSave).toBeDisabled()
    })

    test('shows what the rules would have sent, and changes it as they change', async ({
      alerts,
    }) => {
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await alerts.openRules('Security')
      await expect(alerts.previewSummary).toContainText('out of 4 incidents going on')

      await alerts.choose(alerts.severity, 'Critical only')
      await alerts.choose(alerts.confidence, 'Any, however unsure')

      await expect(alerts.previewSummary).toContainText('would have sent 1 message, out of 4')
      await expect(alerts.previewLeftOut).toContainText('Less serious than critical: 2')
      await expect(alerts.previewLeftOut).toContainText('Already resolved or dismissed: 1')
      await expect(alerts.previewExamples.getByRole('link')).toHaveCount(1)
      await expect(alerts.previewExamples).toContainText('93.184.216.34')
    })

    test('keeps what was chosen, in the card and across a visit', async ({ alerts, page }) => {
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await alerts.openRules('Security')

      await alerts.choose(alerts.severity, 'High or worse')
      await alerts.choose(alerts.sources, 'Wazuh')
      await page.keyboard.press('Escape')
      await alerts.choose(alerts.rate, 'At most 3 messages an hour')
      await alerts.again.uncheck()
      await alerts.detail('Brief').check()
      await alerts.rulesSave.click()

      await expect(alerts.notice).toHaveText('Saved what Security is told.')
      await expect(alerts.rules).toHaveCount(0)
      const summary = alerts.destination('Security').getByTestId('destination-rules')
      await expect(summary).toContainText('high or worse')
      await expect(summary).toContainText('Only from Wazuh')
      await expect(summary).toContainText('At most 3 messages an hour')

      await page.reload()
      await alerts.openRules('Security')
      await expect(alerts.severity).toContainText('High or worse')
      await expect(alerts.sources).toContainText('Wazuh')
      await expect(alerts.again).not.toBeChecked()
      await expect(alerts.detail('Brief')).toBeChecked()
    })

    test('shows the quiet hours when they are on, and will not save an empty one', async ({
      alerts,
    }) => {
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await alerts.openRules('Security')
      await expect(alerts.quietFrom).toHaveCount(0)

      await alerts.quiet.check()
      await alerts.quietFrom.fill('23:00')
      await alerts.quietUntil.fill('23:00')
      await expect(alerts.rulesSave).toBeDisabled()
      await alerts.quietUntil.fill('06:30')
      await alerts.rulesSave.click()

      await expect(alerts.notice).toHaveText('Saved what Security is told.')
      await expect(alerts.destination('Security').getByTestId('destination-rules')).toContainText(
        'Quiet from 23:00 to 06:30',
      )
    })

    test('forgets changes that were not saved', async ({ alerts }) => {
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await alerts.openRules('Security')
      await alerts.choose(alerts.severity, 'Critical only')

      await alerts.rulesCancel.click()
      await expect(alerts.rules).toHaveCount(0)
      await alerts.openRules('Security')

      await expect(alerts.severity).toContainText('Medium or worse')
    })

    test('says why the rules could not be kept, and why a preview could not be made', async ({
      alerts,
      page,
    }) => {
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await page.route('**/api/alerts/destinations/*/preview', (route) => route.abort())
      await alerts.openRules('Security')
      await expect(alerts.previewFailure).toContainText("Can't reach AresGate.")

      await page.route('**/api/alerts/destinations/*/rules', (route) => route.abort())
      await alerts.choose(alerts.severity, 'Critical only')
      await alerts.rulesSave.click()

      await expect(alerts.rulesFailure).toContainText("Can't reach AresGate.")
      await expect(alerts.rules).toBeVisible()
    })
  })

  test('records what was done in the activity, without the address', async ({ alerts, page }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await expect(alerts.destination('Security')).toBeVisible()

    await page.goto('/settings/activity')

    await expect(page.getByText('An alert destination was added')).toBeVisible()
    await expect(page.locator('body')).not.toContainText(TOKEN)
  })

  test.describe('the delivery log', () => {
    const SCAN: IncidentRequest = {
      address: '93.184.216.34',
      severity: 'critical',
      programs: ['wazuh', 'opnsense', 'crowdsec'],
      signals: 8,
      minutes_ago: 0,
    }

    test('is not there before a destination is', async ({ alerts }) => {
      await alerts.goto()
      await expect(alerts.empty).toBeVisible()
      await expect(alerts.log).toHaveCount(0)
    })

    test('says nothing has been sent yet', async ({ alerts }) => {
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)

      await expect(alerts.logEmpty).toContainText('Nothing has been sent yet')
      await expect(alerts.logTotals).toHaveText('Nothing yet.')
    })

    test('shows what was sent, once, and what the message said', async ({
      harness,
      alerts,
      page,
    }) => {
      const discord = await harness.standIn({ kind: 'discord', webhook: `${ID}/${TOKEN}` })
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await alerts.openRules('Security')
      await alerts.choose(alerts.confidence, 'Any, however unsure')
      await alerts.rulesSave.click()
      await expect(alerts.notice).toHaveText('Saved what Security is told.')
      await harness.createIncidents([SCAN])

      expect(await harness.runNotifier()).toEqual({ sent: 1, retrying: 0, failed: 0 })
      expect(await harness.runNotifier()).toEqual({ sent: 0, retrying: 0, failed: 0 })

      await page.reload()
      await expect(alerts.deliveries).toHaveCount(1)
      const sent = alerts.deliveries.first()
      await expect(sent.getByTestId('delivery-state')).toHaveText('Sent')
      await expect(sent.getByTestId('delivery-title')).toContainText('93.184.216.34')
      await expect(sent.getByTestId('delivery-detail')).toContainText('Security · New incident')
      await expect(alerts.logTotals).toHaveText('1 sent, 0 waiting, 0 not sent')
      const messages = await harness.standInRequests(discord.id)
      expect(messages).toHaveLength(1)
      const said = JSON.stringify(messages[0]?.body)
      expect(said).toContain('"allowed_mentions":{"parse":[]}')
      expect(said).toContain('/incidents/')
      expect(said).not.toContain(TOKEN)
      await sent.getByTestId('delivery-title').click()
      await expect(page).toHaveURL(/\/incidents\/\d+$/)
    })

    test('says why a message did not get through, and tries no more', async ({
      harness,
      alerts,
      page,
    }) => {
      await harness.standIn({ kind: 'discord', webhook: `${OTHER_ID}/${OTHER_TOKEN}` })
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await alerts.openRules('Security')
      await alerts.choose(alerts.confidence, 'Any, however unsure')
      await alerts.rulesSave.click()
      await expect(alerts.notice).toHaveText('Saved what Security is told.')
      await harness.createIncidents([SCAN])

      expect(await harness.runNotifier()).toEqual({ sent: 0, retrying: 0, failed: 1 })
      expect(await harness.runNotifier()).toEqual({ sent: 0, retrying: 0, failed: 0 })

      await page.reload()
      await expect(alerts.destination('Security').getByTestId('status')).toHaveText('Problem')
      const failed = alerts.deliveries.first()
      await expect(failed.getByTestId('delivery-state')).toHaveText('Not sent')
      await expect(failed.getByTestId('delivery-note')).toContainText(
        "Discord doesn't accept this webhook (HTTP 404).",
      )
      await expect(alerts.logTotals).toHaveText('0 sent, 0 waiting, 1 not sent')
    })

    test('narrows to a state and says when none match', async ({ harness, alerts }) => {
      await harness.standIn({ kind: 'discord', webhook: `${ID}/${TOKEN}` })
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await alerts.openRules('Security')
      await alerts.choose(alerts.confidence, 'Any, however unsure')
      await alerts.rulesSave.click()
      await expect(alerts.notice).toHaveText('Saved what Security is told.')
      await harness.createIncidents([SCAN])
      await harness.runNotifier()
      await alerts.logRefresh.click()
      await expect(alerts.deliveries).toHaveCount(1)

      await alerts.choose(alerts.logState, 'Not sent')

      await expect(alerts.logEmpty).toContainText('No messages match these filters.')
      await alerts.choose(alerts.logState, 'Sent')
      await expect(alerts.deliveries).toHaveCount(1)
    })
  })
})
