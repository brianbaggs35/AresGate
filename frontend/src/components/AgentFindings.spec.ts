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
})
