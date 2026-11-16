import AgentInvestigation from '@/components/AgentInvestigation.vue'
import { moment } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function open(props: { moments: ReturnType<typeof moment>[]; empty?: string }) {
  const mounted = await mountWithPlugins(AgentInvestigation, { props, signedIn: 'admin' })
  const all = (selector: string) =>
    mounted.wrapper.findAll(`[data-test="${selector}"]`).map((item) => item.text())
  return {
    ...mounted,
    all,
    find: (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`),
  }
}

describe('AgentInvestigation', () => {
  it('says nothing is recorded, or what it is told to say', async () => {
    const plain = await open({ moments: [] })
    const told = await open({ moments: [], empty: 'No agent has looked at this.' })

    expect(plain.find('investigation-none').text()).toBe('Nothing is recorded about this yet.')
    expect(told.find('investigation-none').text()).toBe('No agent has looked at this.')
  })

  it('tells each moment in order: who, what kind, what and the detail when there is one', async () => {
    const { all, find } = await open({
      moments: [
        moment({
          kind: 'handoff',
          title: 'Asked Investigator to look into Incident 4',
          detail: 'It scanned.',
        }),
        moment({
          kind: 'decided',
          agent: 'You',
          agent_id: null,
          title: 'Approved the step: Isolate it',
        }),
      ],
    })

    expect(all('moment-agent')).toEqual(['Orchestrator', 'You'])
    expect(all('moment-kind')).toEqual(['Asked another agent', 'You decided'])
    expect(all('moment-title')).toEqual([
      'Asked Investigator to look into Incident 4',
      'Approved the step: Isolate it',
    ])
    expect(all('moment-detail')).toEqual(['It scanned.'])
    expect(find('investigation-none').exists()).toBe(false)
  })
})
