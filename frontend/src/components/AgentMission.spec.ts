import AgentMission from '@/components/AgentMission.vue'
import { agent, attention, briefing } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function show(props: Partial<InstanceType<typeof AgentMission>['$props']> = {}) {
  const mounted = await mountWithPlugins(AgentMission, {
    props: { agents: [agent()], attention: [], total: 0, briefing: null, ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('AgentMission', () => {
  it('says all is quiet when nothing needs the owner', async () => {
    const { find } = await show()

    expect(find('mission-line').text()).toBe('All quiet: nothing needs you')
    expect(find('mission-needs').exists()).toBe(false)
    expect(find('mission-briefing').exists()).toBe(false)
    expect(find('mission-more').exists()).toBe(false)
  })

  it('says how many agents are at work when nothing needs the owner but they are going', async () => {
    const { find } = await show({
      agents: [agent({ state: 'running' }), agent({ state: 'queued' })],
    })

    expect(find('mission-line').text()).toBe('2 agents at work')
  })

  it('says one agent in the singular', async () => {
    const { find } = await show({ agents: [agent({ state: 'running' })] })

    expect(find('mission-line').text()).toBe('1 agent at work')
  })

  it('names what needs the owner, with the agent, how serious and where to look', async () => {
    const { wrapper, find } = await show({
      attention: [
        attention(),
        attention({
          title: 'Odd logins',
          status: 'ongoing',
          severity: 'medium',
          agent_id: 5,
          action: '',
        }),
      ],
      total: 2,
      agents: [agent({ state: 'running' })],
    })

    expect(find('mission-line').text()).toBe('2 things need you · 1 agent at work')
    const needs = wrapper.findAll('[data-test="mission-need"]')
    expect(needs).toHaveLength(2)
    expect(needs[0]!.text()).toContain('A scan got further than usual')
    expect(needs[0]!.text()).toContain('Night watch')
    expect(needs[0]!.text()).not.toContain('still open')
    expect(needs[0]!.find('[data-test="mission-action"]').text()).toBe(
      'Close port 22 on the router.',
    )
    expect(needs[1]!.find('[data-test="mission-action"]').exists()).toBe(false)
    expect(needs[0]!.attributes('href')).toBe('/agents/3')
    expect(needs[1]!.text()).toContain('still open')
    expect(needs[1]!.attributes('href')).toBe('/agents/5')
  })

  it('says one thing in the singular and how many more there are than shown', async () => {
    const { find } = await show({ attention: [attention()], total: 4 })

    expect(find('mission-line').text()).toBe('4 things need you')
    expect(find('mission-more').text()).toBe("And 3 more in the agents' latest runs.")
    const single = await show({ attention: [attention()], total: 1 })
    expect(single.find('mission-line').text()).toBe('1 thing needs you')
  })

  it('shows the latest briefing and where it came from', async () => {
    const { find } = await show({ briefing: briefing() })

    expect(find('briefing-text').text()).toContain('Nothing needs you today.')
    expect(find('briefing-link').text()).toBe('Morning briefing')
    expect(find('briefing-link').attributes('href')).toBe('/agents/4')
  })
})
