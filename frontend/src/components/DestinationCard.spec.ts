import type { Destination } from '@/api/alerts'
import DestinationCard from '@/components/DestinationCard.vue'
import {
  choices,
  destination,
  emailDestination,
  failing,
  rules,
  threatRules,
  working,
} from '@/test/alerts'
import { mountWithPlugins } from '@/test/mount'

async function show(item: Destination = destination(), props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(DestinationCard, {
    props: { destination: item, choices: choices(), ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  return { ...mounted, find, text }
}

describe('DestinationCard', () => {
  it('names the destination and what kind it is', async () => {
    const { text } = await show()

    expect(text('destination-name')).toBe('Security channel')
    expect(text('destination-kind')).toBe('Discord')
  })

  it('shows where the webhook is without its secret, and says so to a screen reader', async () => {
    const { text } = await show()

    expect(text('destination-address')).toBe(
      'Webhook address, with the secret part hidden: discord.com/api/webhooks/…6789/••••••••',
    )
  })

  it('shows an email destination with its address and mail server', async () => {
    const { text } = await show(emailDestination())

    expect(text('destination-kind')).toBe('Email')
    expect(text('destination-address')).toBe(
      'Email address and the mail server it goes through: me@example.org through smtp.example.com',
    )
  })

  it('says it has not been tried, with a chip for the status', async () => {
    const { text } = await show()

    expect(text('status')).toBe('Not tested yet')
    expect(text('destination-result')).toBe('Not tried yet. Send a test message to check it.')
  })

  it('says a message got through, and when', async () => {
    const { text, find } = await show(working())

    expect(text('status')).toBe('Connected')
    expect(text('destination-result')).toBe('A message last got through 10 minutes ago.')
    expect(find('destination-error').exists()).toBe(false)
  })

  it('says what went wrong with the last message', async () => {
    const { text } = await show(failing())

    expect(text('status')).toBe('Problem')
    expect(text('destination-error')).toContain("Discord doesn't accept this webhook (HTTP 404).")
    expect(text('destination-result')).toContain('The last try failed.')
  })

  it('says when it is turned off', async () => {
    const { text, find } = await show(destination({ enabled: false }))

    expect(text('destination-off')).toBe('Turned off')
    expect(find('destination-enabled').text()).toContain('Not sending')
    expect((await show()).find('destination-off').exists()).toBe(false)
  })

  it('cannot test a destination whose address is gone', async () => {
    const { find } = await show(destination({ status: 'not_connected' }))

    expect(find('destination-test').attributes('disabled')).toBeDefined()
    expect(find('destination-result').text()).toBe('Its webhook address is gone.')
  })

  it('says in words what it is told about', async () => {
    const { text } = await show()
    expect(text('destination-rules')).toBe(
      'Tells you about incidents that are medium or worse, when AresGate is at least 65% sure. From any program. At most 6 messages an hour.',
    )

    const chosen = await show(
      destination({ rules: rules({ sources: ['wazuh'], quiet_hours: true }) }),
    )
    expect(chosen.text('destination-rules')).toContain('Only from Wazuh.')
    expect(chosen.text('destination-rules')).toContain('Quiet from 22:00 to 07:00 (UTC)')
  })

  it('asks to test, set the rules of, change and remove it', async () => {
    const { find, wrapper } = await show()

    await find('destination-test').trigger('click')
    await find('destination-rules-edit').trigger('click')
    await find('destination-edit').trigger('click')
    await find('destination-remove').trigger('click')

    expect(wrapper.emitted('test')).toHaveLength(1)
    expect(wrapper.emitted('rules')).toHaveLength(1)
    expect(wrapper.emitted('edit')).toHaveLength(1)
    expect(wrapper.emitted('remove')).toHaveLength(1)
  })

  it('says in words that a destination told of threats is told of real attacks', async () => {
    const { text } = await show(destination({ rules: threatRules() }))

    expect(text('destination-rules')).toContain('Tells you only about real attacks')
  })

  it('asks to send a sample alert', async () => {
    const { find, wrapper } = await show()

    await find('destination-sample').trigger('click')

    expect(wrapper.emitted('sample')).toHaveLength(1)
  })

  it('cannot send a sample alert to a destination whose address is gone', async () => {
    const { find } = await show(destination({ status: 'not_connected' }))

    expect(find('destination-sample').attributes('disabled')).toBeDefined()
  })

  it('shows the sample alert as being sent', async () => {
    const { find } = await show(destination(), { busy: true, sampling: true })

    expect(find('destination-sample').classes()).toContain('v-btn--loading')
    expect(find('destination-test').classes()).not.toContain('v-btn--loading')
  })

  it('asks to turn it off, and on again', async () => {
    const off = await show()
    await off.find('destination-enabled').find('input').setValue(false)
    expect(off.wrapper.emitted('toggle')).toEqual([[false]])

    const on = await show(destination({ enabled: false }))
    await on.find('destination-enabled').find('input').setValue(true)
    expect(on.wrapper.emitted('toggle')).toEqual([[true]])
  })

  it('waits while something is being done to it', async () => {
    const { find } = await show(destination(), { busy: true })

    for (const name of ['test', 'sample', 'rules-edit', 'edit', 'remove']) {
      expect(find(`destination-${name}`).attributes('disabled')).toBeDefined()
    }
    expect(find('destination-enabled').find('input').attributes('disabled')).toBeDefined()
  })

  it('shows the test as under way', async () => {
    const { find } = await show(destination(), { busy: true, testing: true })

    expect(find('destination-test').classes()).toContain('v-btn--loading')
  })
})
