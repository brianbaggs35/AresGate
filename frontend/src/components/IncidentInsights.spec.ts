import IncidentInsights from '@/components/IncidentInsights.vue'
import { insights } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(changes: Parameters<typeof insights>[0] = {}) {
  const { wrapper } = await mountWithPlugins(IncidentInsights, {
    props: { insights: insights(changes) },
  })
  return wrapper
}

describe('IncidentInsights', () => {
  it('says what each program told and what it added', async () => {
    const wrapper = await show()

    const programs = wrapper.findAll('[data-test="insight-programs"] > li')
    expect(programs).toHaveLength(2)
    expect(programs[0]?.text()).toContain('Wazuh')
    expect(programs[0]?.text()).toContain('12 alerts')
    expect(programs[0]?.find('[data-test="insight-adds"]').text()).toContain(
      'MITRE ATT&CK techniques',
    )
    // A program that said no more than the basics is listed as one that did.
    expect(programs[1]?.text()).toContain('3 alerts')
    expect(programs[1]?.find('[data-test="insight-basics"]').text()).toBe(
      'Only the basics: what, where and when.',
    )
  })

  it('says a single alert in the singular', async () => {
    const wrapper = await show({
      programs: [{ source: 'wazuh', source_name: 'Wazuh', reports: 1, adds: [] }],
    })

    expect(wrapper.find('[data-test="insight-programs"]').text()).toContain('1 alert ')
  })

  it('draws the techniques, machines, applications, what was named and the groups', async () => {
    const wrapper = await show()

    expect(wrapper.find('[data-test="insight-techniques"]').text()).toContain('T1110 Brute Force')
    expect(wrapper.find('[data-test="insight-techniques"]').text()).toContain('Credential Access')
    expect(wrapper.find('[data-test="insight-hosts"]').text()).toContain('web1 (192.168.1.20)')
    expect(wrapper.find('[data-test="insight-apps"]').text()).toContain('ssh')
    expect(wrapper.find('[data-test="insight-named-hostname"]').text()).toContain(
      'scanner.example.net',
    )
    expect(wrapper.find('[data-test="insight-tags"]').text()).toContain('sshd')
  })

  it('leaves out what no program said', async () => {
    const wrapper = await show({
      techniques: [],
      tags: [],
      hosts: [],
      apps: [],
      named: [],
    })

    for (const absent of [
      'insight-techniques',
      'insight-hosts',
      'insight-apps',
      'insight-named-hostname',
      'insight-tags',
    ]) {
      expect(wrapper.find(`[data-test="${absent}"]`).exists()).toBe(false)
    }
  })

  it('draws a technique without a tactic without one', async () => {
    const wrapper = await show({
      techniques: [{ id: 'T1078', tactic: '', technique: 'Valid Accounts', count: 2 }],
    })

    expect(wrapper.find('[data-test="insight-techniques"]').text()).not.toContain('(')
  })
})
