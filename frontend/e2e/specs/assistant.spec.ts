import type { IncidentRequest } from '../support'
import { expect, test, turnOnAi } from '../support'

const ATTACKER = '93.184.216.34'

/** A scan that two programs saw, of a device on the network that is known by name. */
const SCAN: IncidentRequest = {
  address: ATTACKER,
  severity: 'high',
  programs: ['wazuh', 'opnsense'],
  signals: 4,
  minutes_ago: 4,
  device_name: 'nas',
}

const ATTENTION = 'What needs my attention right now?'

test.describe('the assistant', () => {
  test('is a place in the menu, and suggests what to ask before anything was', async ({
    page,
    shell,
    assistant,
  }) => {
    await page.goto('/')

    await shell.goTo('assistant')

    await expect(page).toHaveURL('/assistant')
    await expect(assistant.heading).toHaveText('Assistant')
    await expect(assistant.empty).toContainText('Ask about your network')
    await expect(assistant.starters).toHaveCount(4)
    await assistant.starters.first().click()
    await expect(assistant.input).toHaveValue(ATTENTION)
  })

  test('says AI is off, and what the answer to a question then is', async ({ assistant }) => {
    await assistant.goto()
    await expect(assistant.off).toContainText('AI is off')

    await assistant.ask(ATTENTION)

    await expect(assistant.failedAnswer).toContainText('AI is turned off.')
    await expect(assistant.ownerMessages).toHaveText(ATTENTION)
    await assistant.showConversations()
    await expect(assistant.conversations).toHaveCount(1)
  })

  test('looks up what needs attention, answers, and links to what it is based on', async ({
    harness,
    aiSettings,
    assistant,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await assistant.goto()
    await expect(assistant.off).toHaveCount(0)

    await assistant.ask(ATTENTION)

    await expect(assistant.answers).toContainText('Start with incident')
    await expect(assistant.lookups).toHaveText(['1 open incident'])
    await expect(assistant.busy).toHaveCount(0)
    await expect(page).toHaveURL(/\/assistant\/\d+$/)
    await assistant.showConversations()
    await expect(assistant.conversations).toHaveCount(1)
    await assistant.hideConversations()
    await expect(assistant.input).toHaveValue('')

    await assistant.cites.first().click()

    await expect(page).toHaveURL(/\/incidents\/\d+$/)
  })

  test('looks up a device, and links to its page', async ({
    harness,
    aiSettings,
    assistant,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await assistant.goto()

    await assistant.ask('What is on the storage?')

    await expect(assistant.answers).toContainText('Start with device')
    await expect(assistant.lookups).toHaveText(['1 device'])
    await expect(assistant.cites).toHaveText(['nas'])

    await assistant.cites.first().click()

    await expect(page).toHaveURL(/\/assets\/device-\d+$/)
  })

  test('shows exactly what the provider was sent, one request for each time it was asked', async ({
    harness,
    aiSettings,
    assistant,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await assistant.goto()
    await assistant.ask(ATTENTION)
    await expect(assistant.answers).toContainText('Start with incident')

    await expect(assistant.calls).toHaveText([
      'See what was sent (1 of 2)',
      'See what was sent (2 of 2)',
    ])
    await assistant.calls.last().click()

    await expect(assistant.callDialog).toContainText(`The owner asks: ${ATTENTION}`)
    // The first request had nothing looked up; the second has what was.
    await expect(assistant.callDialog).toContainText('open incidents')
  })

  test('answers a question that needs nothing looked up, and keeps going in the same conversation', async ({
    harness,
    aiSettings,
    assistant,
    page,
  }) => {
    await turnOnAi(harness, aiSettings)
    await assistant.goto()

    await assistant.ask('How are you?')
    await expect(assistant.answers).toContainText('All quiet on the home network.')
    await expect(assistant.lookups).toHaveCount(0)
    const address = page.url()

    await assistant.ask('And now?')

    await expect(assistant.answers).toHaveCount(2)
    await expect(assistant.ownerMessages).toHaveText(['How are you?', 'And now?'])
    expect(page.url()).toBe(address)
  })

  test('keeps conversations, opens another, and deletes one after asking', async ({
    harness,
    aiSettings,
    assistant,
    page,
  }) => {
    await turnOnAi(harness, aiSettings)
    await assistant.goto()
    await assistant.ask('First question')
    await expect(assistant.answers).toHaveCount(1)
    await assistant.newConversation.click()
    await expect(assistant.empty).toBeVisible()
    await assistant.ask('Second question')
    await expect(assistant.answers).toHaveCount(1)
    await assistant.showConversations()
    await expect(assistant.conversations).toHaveCount(2)

    await page.reload()
    await expect(assistant.ownerMessages).toHaveText(['Second question'])
    await assistant.openConversation('First question')
    await expect(assistant.ownerMessages).toHaveText(['First question'])

    await assistant.showConversations()
    await assistant.deleteButton(assistant.conversations.filter({ hasText: 'First' })).click()
    await assistant.confirm.click()

    await expect(page).toHaveURL('/assistant')
    await expect(assistant.empty).toBeVisible()
    await assistant.showConversations()
    await expect(assistant.conversations).toHaveCount(1)
  })

  test('asks again after an answer that could not be made', async ({
    harness,
    aiSettings,
    assistant,
  }) => {
    await assistant.goto()
    await assistant.ask('Anything odd?')
    await expect(assistant.failedAnswer).toContainText('AI is turned off.')
    await turnOnAi(harness, aiSettings)
    await assistant.goto('')
    await assistant.openConversation()
    await expect(assistant.failedAnswer).toBeVisible()

    await assistant.retry.click()

    await expect(assistant.failedAnswer).toHaveCount(0)
    await expect(assistant.answers).toContainText('All quiet on the home network.')
    await expect(assistant.ownerMessages).toHaveText(['Anything odd?'])
  })

  test('is asked about an incident from its page, with the question ready to send', async ({
    harness,
    aiSettings,
    incident,
    incidents,
    assistant,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await incidents.goto('?view=all')
    await incidents.cards.first().click()

    await incident.aiChat.click()

    await expect(page).toHaveURL(/\/assistant\?about=incident:\d+$/)
    await expect(assistant.input).toHaveValue(/What should I know about incident \d+/)
    await assistant.send.click()
    await expect(assistant.answers).toContainText('All quiet')
  })

  test('says a conversation is not there', async ({ assistant }) => {
    await assistant.goto('/4040')

    await expect(assistant.error).toContainText('There is no such conversation.')
  })
})
