import AgentHandoffs from '@/components/AgentHandoffs.vue'
import { handoff, handoffs } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function open(list = handoffs({ handoffs: [handoff()], made_today: 1 })) {
  const mounted = await mountWithPlugins(AgentHandoffs, { props: { list }, signedIn: 'admin' })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('AgentHandoffs', () => {
  it('says what the limits are and how many have been made today', async () => {
    const { find } = await open()

    expect(find('handoffs-limits').text()).toBe(
      'Agents may ask each other 2 levels deep, never in a circle, and 10 times a day: 1 so far today.',
    )
  })

  it('says when no agent has asked another for help', async () => {
    const { find } = await open(handoffs())

    expect(find('handoffs-none').text()).toContain('No agent has asked another')
    expect(find('handoffs-list').exists()).toBe(false)
  })

  it('says who asked whom, about what and why, with links', async () => {
    const { find } = await open()

    expect(find('handoff-from').attributes('href')).toBe('/agents/3')
    expect(find('handoff-to').attributes('href')).toBe('/agents/4')
    expect(find('handoff-status').text()).toBe('Asked')
    expect(find('handoff-subject').text()).toBe('About Incident 12: It scanned three devices.')
    expect(find('handoff-incident').attributes('href')).toBe('/incidents/12')
    expect(find('handoff-refusal').exists()).toBe(false)
  })

  it('says why one was refused, and does not link an agent that was not there', async () => {
    const { find } = await open(
      handoffs({
        handoffs: [
          handoff({
            status: 'refused',
            refusal: 'You have no Incident investigator agent that is on.',
            to_agent_id: null,
            incident_id: null,
            subject: 'Device 2',
          }),
        ],
      }),
    )

    expect(find('handoff-status').text()).toBe('Refused')
    expect(find('handoff-to').element.tagName).toBe('SPAN')
    expect(find('handoff-refusal').text()).toContain('no Incident investigator agent')
    expect(find('handoff-incident').exists()).toBe(false)
    expect(find('handoff-subject').text()).toContain('About Device 2')
  })
})
