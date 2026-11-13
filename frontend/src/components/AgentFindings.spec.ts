import AgentFindings from '@/components/AgentFindings.vue'
import { finding } from '@/test/agents'
import { mountWithPlugins } from '@/test/mount'

async function open(findings = [finding()]) {
  return mountWithPlugins(AgentFindings, { props: { findings } })
}

describe('AgentFindings', () => {
  it('says how serious each is, what it is and why', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="severity"]').text()).toBe('High')
    expect(wrapper.find('[data-test="finding-title"]').text()).toBe('A scan got further than usual')
    expect(wrapper.find('[data-test="finding-detail"]').text()).toBe(
      'Check the firewall rule for port 22.',
    )
  })

  it('shows what it rests on and how to check it, when the agent said', async () => {
    const { wrapper } = await open([
      finding({
        evidence: ['Eleven connections to port 22 in an hour.', 'Refused by rule 4.'],
        verify: 'Look at the firewall log for port 22.',
        benign: 'You were testing SSH yourself.',
      }),
    ])

    expect(wrapper.findAll('[data-test="finding-fact"]').map((fact) => fact.text())).toEqual([
      'Eleven connections to port 22 in an hour.',
      'Refused by rule 4.',
    ])
    expect(wrapper.find('[data-test="finding-verify"]').text()).toContain(
      'Look at the firewall log for port 22.',
    )
    expect(wrapper.find('[data-test="finding-benign"]').text()).toContain(
      'You were testing SSH yourself.',
    )
  })

  it('shows only the one of how to check it and what would make it harmless that there is', async () => {
    const { wrapper } = await open([finding({ benign: 'It is the backup job.' })])

    expect(wrapper.find('[data-test="finding-evidence"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="finding-verify"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="finding-benign"]').exists()).toBe(true)
  })

  it('puts the most serious first', async () => {
    const { wrapper } = await open([
      finding({ severity: 'low', title: 'Minor' }),
      finding({ severity: 'critical', title: 'Major' }),
      finding({ severity: 'mysterious', title: 'Unknown' }),
    ])

    expect(wrapper.findAll('[data-test="finding-title"]').map((title) => title.text())).toEqual([
      'Major',
      'Minor',
      'Unknown',
    ])
    expect(wrapper.findAll('[data-test="severity"]')[2]!.text()).toBe('Info')
  })

  it('links what it is based on where there is a page for it', async () => {
    const { wrapper } = await open([
      finding({
        cites: [
          { kind: 'incident', key: '4', label: 'Incident 4' },
          { kind: 'integration', key: 'wazuh', label: 'Wazuh' },
          { kind: 'device', key: 'x', label: 'A device' },
        ],
      }),
    ])

    const cites = wrapper.findAll('[data-test="finding-cite"]')
    expect(cites.map((cite) => cite.text())).toEqual(['Incident 4', 'Wazuh', 'A device'])
    expect(cites[0]!.attributes('href')).toBe('/incidents/4')
    expect(cites[1]!.attributes('href')).toBe('/integrations/wazuh')
    expect(cites[2]!.attributes('href')).toBeUndefined()
  })

  it('leaves out what has nothing to say', async () => {
    const { wrapper } = await open([finding({ detail: '', cites: [] })])

    expect(wrapper.find('[data-test="finding-detail"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="finding-cites"]').exists()).toBe(false)
  })

  it('says whether the last run already reported it', async () => {
    const { wrapper } = await open([
      finding({ title: 'Fresh', status: 'new' }),
      finding({ title: 'Old news', status: 'ongoing', severity: 'low' }),
    ])

    expect(wrapper.findAll('[data-test="finding-status"]').map((chip) => chip.text())).toEqual([
      'New',
      'Still open',
    ])
  })

  it('says what to do and how sure the agent is, and leaves out what to do when there is nothing', async () => {
    const { wrapper } = await open([
      finding(),
      finding({ title: 'Nothing to do', action: '', confidence: 'low' }),
    ])

    const actions = wrapper.findAll('[data-test="finding-action"]')
    expect(actions).toHaveLength(1)
    expect(actions[0]!.text()).toBe('What to do: Close port 22 on the router.')
    expect(wrapper.findAll('[data-test="finding-confidence"]').map((each) => each.text())).toEqual([
      'Sure',
      'Not very sure',
    ])
  })

  it('says how long it has been reported', async () => {
    const { wrapper } = await open([
      finding(),
      finding({
        title: 'Again',
        runs_seen: 4,
        status: 'ongoing',
        first_seen_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
      }),
    ])

    expect(wrapper.findAll('[data-test="finding-history"]').map((each) => each.text())).toEqual([
      'First time it was reported',
      'Reported in 4 runs in a row, since 2 days ago',
    ])
  })
})
