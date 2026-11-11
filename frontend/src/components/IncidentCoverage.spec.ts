import IncidentCoverage from '@/components/IncidentCoverage.vue'
import { mountWithPlugins } from '@/test/mount'

describe('IncidentCoverage', () => {
  it('lists the programs that reported and those that are not connected, with what they add', async () => {
    const { wrapper } = await mountWithPlugins(IncidentCoverage, {
      props: {
        sources: [{ key: 'wazuh', name: 'Wazuh' }],
        missing: [
          { source: 'ntopng', source_name: 'ntopng', adds: 'Who each flow was between.' },
          { source: 'virustotal', source_name: 'VirusTotal', adds: 'What the engines make of it.' },
        ],
      },
    })

    const seen = wrapper.findAll('[data-test="coverage-seen"]')
    expect(seen).toHaveLength(1)
    expect(seen[0]?.text()).toContain('Wazuh')
    expect(seen[0]?.text()).toContain('Reported part of this incident.')
    const missing = wrapper.findAll('[data-test="coverage-missing"]')
    expect(missing.map((each) => each.find('[data-test="coverage-name"]').text())).toEqual([
      'ntopng',
      'VirusTotal',
    ])
    expect(missing[0]?.text()).toContain('Not connected. Would add: Who each flow was between.')
  })

  it('points each missing program to where it is connected', async () => {
    const { wrapper, router } = await mountWithPlugins(IncidentCoverage, {
      props: {
        sources: [],
        missing: [{ source: 'wazuh', source_name: 'Wazuh', adds: 'The log line.' }],
      },
    })

    const button = wrapper.find('[data-test="coverage-connect-wazuh"]')
    expect(button.text()).toBe('Connect Wazuh')
    expect(router.resolve({ name: 'integration', params: { key: 'wazuh' } }).href).toBe(
      '/integrations/wazuh',
    )
    expect(button.attributes('href')).toBe('/integrations/wazuh')
  })
})
