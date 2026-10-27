import ResponseDetails from '@/components/ResponseDetails.vue'
import { ban, incident, response } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

const NOW = Date.now()
const at = (minutes: number) => new Date(NOW + minutes * 60_000).toISOString()

async function show(changes: Parameters<typeof response>[0], neighbours = 0) {
  const { wrapper } = await mountWithPlugins(ResponseDetails, {
    props: {
      incident: incident({
        first_seen_at: at(-60),
        last_seen_at: at(-50),
        neighbours,
        response: response(changes),
      }),
      now: NOW,
    },
  })
  const text = (selector: string) => wrapper.find(`[data-test="${selector}"]`).text()
  const all = (selector: string) => wrapper.findAll(`[data-test="${selector}"]`)
  return { wrapper, text, all }
}

describe('ResponseDetails', () => {
  it('says that a ban holds, who made it, why and how long it lasts', async () => {
    const { text, all } = await show({
      state: 'banned',
      label: 'Banned',
      bans: [ban({ seen_at: at(-48), ends_at: at(192) })],
    })

    expect(text('response-state')).toBe('Banned')
    expect(text('response-headline')).toBe(
      'CrowdSec banned 93.184.216.34. The ban has 3h 12m left.',
    )
    expect(all('response-ban')).toHaveLength(1)
    expect(text('response-ban-address')).toBe('93.184.216.34')
    expect(text('response-ban-status')).toBe('In force')
    expect(text('response-ban-reason')).toBe("crowdsecurity/ssh-bf · CrowdSec's own detection")
    expect(text('response-ban-ends')).toContain('in 3h 12m.')
  })

  it('says that a ban ended, and leaves out what it does not know of it', async () => {
    const { text, wrapper } = await show({
      state: 'ban_ended',
      label: 'Ban ended',
      bans: [ban({ in_force: false, ends_at: at(-30), scenario: null, origin: null })],
    })

    expect(text('response-ban-status')).toBe('Ended')
    expect(wrapper.find('[data-test="response-ban-reason"]').exists()).toBe(false)
    expect(text('response-ban-ends')).toMatch(/^Ran out /)
  })

  it('lists the steps in order', async () => {
    const { all } = await show({
      state: 'banned',
      label: 'Banned',
      bans: [ban({ seen_at: at(-48), ends_at: at(192) })],
      blocked: 3,
      blocked_since_ban: 3,
      last_blocked_at: at(-5),
    })

    expect(all('response-step-title').map((title) => title.text())).toEqual([
      'First seen',
      'Banned',
      'Still trying',
      'Ban ends',
    ])
  })

  it('says what else turned the address away', async () => {
    const { text } = await show({
      state: 'blocked',
      label: 'Blocked',
      blocked: 14,
      dropped: 2,
      last_blocked_at: at(-3),
    })

    expect(text('fact-firewall')).toContain('Turned it away 14 times.')
    expect(text('fact-suricata')).toContain('Stopped 2 alerts.')
  })

  it('says what it cannot tell', async () => {
    const { all } = await show({
      state: 'none',
      label: 'No response yet',
      unknown: ["CrowdSec isn't connected, so AresGate can't see whether it banned it."],
    })

    expect(all('response-note').map((note) => note.text())).toEqual([
      "CrowdSec isn't connected, so AresGate can't see whether it banned it.",
    ])
  })

  it('has no bans, facts, steps or notes to list when there is nothing to list', async () => {
    const { wrapper, text } = await show({ state: 'none', label: 'No response yet' })

    expect(text('response-state')).toBe('No response yet')
    for (const part of ['response-bans', 'response-facts', 'response-steps', 'response-unknown']) {
      expect(wrapper.find(`[data-test="${part}"]`).exists()).toBe(false)
    }
  })

  it('counts from now unless told when it is', async () => {
    const { wrapper } = await mountWithPlugins(ResponseDetails, {
      props: {
        incident: incident({
          response: response({ state: 'banned', label: 'Banned', bans: [ban()] }),
        }),
      },
    })

    expect(wrapper.find('[data-test="response-headline"]').text()).toMatch(/left\.$/)
  })
})
