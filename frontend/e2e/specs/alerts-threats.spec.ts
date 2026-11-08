import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const ID = '1234567890123456789'
const TOKEN = 'Zk3-_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-_x'
const ADDRESS = `https://discord.com/api/webhooks/${ID}/${TOKEN}`
const ATTACKER = '93.184.216.34'
const BOT = '8.8.4.10'

/** An address that scanned, tried a flaw and then was heard from by a device it got into: a real
 * attack going on now. */
const ATTACK: IncidentRequest = {
  address: ATTACKER,
  severity: 'critical',
  programs: ['wazuh', 'opnsense'],
  signals: 4,
  exploit: true,
  compromise: true,
  minutes_ago: 0,
  device_name: 'nas',
}

/** A bot that swept the network in waves, as all of the internet does all day: noise. */
const SWEEP: IncidentRequest = {
  address: BOT,
  severity: 'low',
  programs: ['opnsense'],
  signals: 9,
  scan: true,
  neighbours: 3,
  waves: 3,
  ports: [22, 80, 443],
  minutes_ago: 0,
}

test.describe('alerts for real attacks', () => {
  test('a new channel is told of real attacks only, and says what that means', async ({
    alerts,
  }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await alerts.openRules('Security')

    await expect(alerts.purposes).toBeVisible()
    await expect(alerts.purpose('threats')).toContainText('Recommended')
    await expect(alerts.purposeChosen('threats')).toBeChecked()
    await expect(alerts.threatsNote).toContainText('A message goes out when an incident becomes')
    await expect(alerts.threatsNote).toContainText('stood down')
    await expect(alerts.floors).toHaveCount(0)
    await expect(alerts.threatsLink).toHaveAttribute('href', '/settings/threat-detection')
  })

  test('the link beside the cards goes to where it is set what a threat is', async ({
    alerts,
    page,
  }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await alerts.openRules('Security')

    await alerts.threatsLink.click()

    await expect(page).toHaveURL('/settings/threat-detection')
  })

  test('the cards change the rules under them, and "everything serious" becomes custom when they are', async ({
    alerts,
  }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await alerts.openRules('Security')

    await alerts.purpose('serious').click()
    await expect(alerts.purposeChosen('serious')).toBeChecked()
    await expect(alerts.severity).toContainText('Medium or worse')
    await expect(alerts.confidence).toContainText('High: 65% or more')

    await alerts.choose(alerts.severity, 'Critical only')
    await expect(alerts.purposeChosen('custom')).toBeChecked()

    await alerts.purpose('threats').click()
    await expect(alerts.floors).toHaveCount(0)
    await alerts.purpose('serious').click()
    await expect(alerts.severity).toContainText('Medium or worse')
  })

  test('keeps the choice of cards across a visit', async ({ alerts, page }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await alerts.openRules('Security')
    await alerts.purpose('serious').click()
    await alerts.rulesSave.click()
    await expect(alerts.notice).toHaveText('Saved what Security is told.')

    await page.reload()
    await alerts.openRules('Security')
    await expect(alerts.purposeChosen('serious')).toBeChecked()

    await alerts.purpose('threats').click()
    await alerts.rulesSave.click()
    await expect(alerts.notice).toHaveText('Saved what Security is told.')
    await page.reload()
    await expect(alerts.destination('Security').getByTestId('destination-rules')).toContainText(
      'Tells you only about real attacks',
    )
  })

  test('shows the message as Discord will, and the later message of the story', async ({
    alerts,
  }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await alerts.openRules('Security')

    await expect(alerts.discord).toBeVisible()
    await expect(alerts.discordTitle).toContainText('Attack in progress')
    await expect(alerts.discordDescription).toContainText('Why AresGate thinks so')
    await expect(alerts.discordFields).toContainText('How far it got')
    await expect(alerts.discordFooter).toHaveText('AresGate · sample alert')

    await alerts.story('worse').click()
    await expect(alerts.discordTitle).toContainText('Escalated')
    await expect(alerts.discordDescription).toContainText('gone further since the last message')

    await alerts.story('new').click()
    await expect(alerts.discordTitle).not.toContainText('Escalated')
  })

  test('shows more of the message as more is chosen to be said', async ({ alerts }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await alerts.openRules('Security')
    await expect(alerts.discordFields).toContainText('Seen from')
    await expect(alerts.discordFields).not.toContainText('On your network')

    await alerts.detail('Brief').check()
    await expect(alerts.discordFields).not.toContainText('Seen from')

    await alerts.detail('Full').check()
    await expect(alerts.discordFields).toContainText('On your network')
    await expect(alerts.discordFields).toContainText('living-room-tv')
  })

  test('shows a message of the other kind when the other card is chosen', async ({ alerts }) => {
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await alerts.openRules('Security')
    await expect(alerts.discordFields).toContainText('How far it got')
    await expect(alerts.discordTitle).toContainText('Attack in progress')

    await alerts.purpose('serious').click()

    // The other kind of message is for something less than a threat, and says why all the same.
    await expect(alerts.discordTitle).toContainText('High-severity')
    await expect(alerts.discordTitle).not.toContainText('Attack in progress')
    await expect(alerts.discordDescription).toContainText('Why AresGate thinks so')
    await expect(alerts.discordFields).toContainText('How sure')
    await expect(alerts.discordFooter).toHaveText('AresGate · sample alert')
  })

  test('says why a sample message could not be made', async ({ alerts, page }) => {
    await page.route('**/api/alerts/sample**', (route) => route.abort())
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)

    await alerts.openRules('Security')

    await expect(alerts.sampleFailure).toContainText("Can't reach AresGate.")
    await expect(alerts.discord).toHaveCount(0)
  })

  test('sends a sample alert to the channel, marked as one', async ({ harness, alerts }) => {
    const discord = await harness.standIn({ kind: 'discord', webhook: `${ID}/${TOKEN}` })
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    const card = alerts.destination('Security')

    await card.getByTestId('destination-sample').click()

    await expect(alerts.notice).toHaveText(
      'A sample alert was sent to Security. Look for it in the channel.',
    )
    await expect(card.getByTestId('status')).toHaveText('Connected')
    const [message] = await harness.standInRequests(discord.id)
    expect(message?.path).toBe(`/api/webhooks/${ID}/${TOKEN}`)
    const said = JSON.stringify(message?.body)
    expect(said).toContain('AresGate · sample alert')
    expect(said).toContain('Why AresGate thinks so')
    expect(said).toContain('"allowed_mentions":{"parse":[]}')
    expect(said).not.toContain(TOKEN)
  })

  test('says why a sample alert did not get through', async ({ harness, alerts }) => {
    await harness.standIn({
      kind: 'discord',
      webhook: '9876543210987654321/Qq9-_zyxwvutsrqponmlkjihgfedcba',
    })
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    const card = alerts.destination('Security')

    await card.getByTestId('destination-sample').click()

    await expect(card.getByTestId('status')).toHaveText('Problem')
    await expect(card.getByTestId('destination-error')).toContainText(
      "Discord doesn't accept this webhook (HTTP 404).",
    )
    await expect(alerts.notice).toHaveCount(0)
  })

  test('tells of the attack and not of the noise, with the reason', async ({
    harness,
    alerts,
    page,
  }) => {
    const discord = await harness.standIn({ kind: 'discord', webhook: `${ID}/${TOKEN}` })
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await expect(alerts.destination('Security')).toBeVisible()
    await harness.createIncidents([ATTACK, SWEEP])

    expect(await harness.runNotifier()).toEqual({ sent: 1, retrying: 0, failed: 0 })
    expect(await harness.runNotifier()).toEqual({ sent: 0, retrying: 0, failed: 0 })

    const messages = await harness.standInRequests(discord.id)
    expect(messages).toHaveLength(1)
    const said = JSON.stringify(messages[0]?.body)
    expect(said).toContain(ATTACKER)
    expect(said).not.toContain(BOT)
    expect(said).toContain('Why AresGate thinks so')
    expect(said).toContain('AresGate · threat alert')
    expect(said).toContain('/incidents/')
    expect(said).not.toContain(TOKEN)
    await page.reload()
    await expect(alerts.deliveries).toHaveCount(1)
    await expect(alerts.deliveries.first().getByTestId('delivery-state')).toHaveText('Sent')
  })

  test('stands the message down when the incident turns out not to be a threat', async ({
    harness,
    alerts,
    page,
  }) => {
    const discord = await harness.standIn({ kind: 'discord', webhook: `${ID}/${TOKEN}` })
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await expect(alerts.destination('Security')).toBeVisible()
    await harness.createIncidents([ATTACK])
    expect(await harness.runNotifier()).toEqual({ sent: 1, retrying: 0, failed: 0 })

    await harness.createVerdicts([{ verdict: 'not_suspicious', address: ATTACKER }])

    expect(await harness.runNotifier()).toEqual({ sent: 1, retrying: 0, failed: 0 })
    expect(await harness.runNotifier()).toEqual({ sent: 0, retrying: 0, failed: 0 })
    const [told, changed, ...rest] = await harness.standInRequests(discord.id)
    expect(rest).toHaveLength(0)
    expect(told?.method).toBe('POST')
    expect(changed?.method).toBe('PATCH')
    expect(changed?.path).toMatch(new RegExp(`^/api/webhooks/${ID}/${TOKEN}/messages/\\d+$`))
    const said = JSON.stringify(changed?.body)
    expect(said).toContain('Stood down:')
    expect(said).toContain('no longer a threat')
    expect(said).toContain('AresGate · stood down')

    await page.reload()
    await expect(alerts.deliveries).toHaveCount(2)
    const update = alerts.deliveries.first()
    await expect(update.getByTestId('delivery-title')).toContainText('Stood down:')
    await expect(update.getByTestId('delivery-detail')).toContainText('Message changed: stood down')
    await expect(update.getByTestId('delivery-state')).toHaveText('Sent')
  })

  test('tells again when the attack goes a stage further, in the message it already sent', async ({
    harness,
    alerts,
  }) => {
    const discord = await harness.standIn({ kind: 'discord', webhook: `${ID}/${TOKEN}` })
    await alerts.goto()
    await alerts.addDestination('Security', ADDRESS)
    await expect(alerts.destination('Security')).toBeVisible()
    await harness.createIncidents([{ ...ATTACK, compromise: false }])
    expect(await harness.runNotifier()).toEqual({ sent: 1, retrying: 0, failed: 0 })

    await harness.createIncidents([ATTACK])
    expect(await harness.runNotifier()).toEqual({ sent: 1, retrying: 0, failed: 0 })
    expect(await harness.runNotifier()).toEqual({ sent: 0, retrying: 0, failed: 0 })

    const messages = await harness.standInRequests(discord.id)
    expect(messages).toHaveLength(2)
    expect(JSON.stringify(messages[0]?.body)).toContain('Attack in progress')
    expect(JSON.stringify(messages[0]?.body)).not.toContain('Escalated:')
    expect(JSON.stringify(messages[1]?.body)).toContain('Escalated: Possible break-in')
  })

  test.describe('rules of the owner’s own', () => {
    test('still tell of what is serious, as before', async ({ harness, alerts }) => {
      const discord = await harness.standIn({ kind: 'discord', webhook: `${ID}/${TOKEN}` })
      await alerts.goto()
      await alerts.addDestination('Security', ADDRESS)
      await alerts.openRules('Security')
      await alerts.purpose('custom').click()
      await alerts.choose(alerts.confidence, 'Any, however unsure')
      await alerts.rulesSave.click()
      await expect(alerts.notice).toHaveText('Saved what Security is told.')
      await harness.createIncidents([
        {
          address: BOT,
          severity: 'high',
          programs: ['wazuh', 'opnsense'],
          signals: 3,
          minutes_ago: 0,
        },
      ])

      expect(await harness.runNotifier()).toEqual({ sent: 1, retrying: 0, failed: 0 })

      const [message] = await harness.standInRequests(discord.id)
      const said = JSON.stringify(message?.body)
      expect(said).toContain(BOT)
      expect(said).not.toContain('AresGate · threat alert')
    })
  })
})
