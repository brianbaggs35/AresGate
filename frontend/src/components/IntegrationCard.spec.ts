import type { IntegrationSummary } from '@/api/integrations'
import IntegrationCard from '@/components/IntegrationCard.vue'
import { summary } from '@/test/integrations'
import { mountWithPlugins } from '@/test/mount'

async function show(overrides: Partial<IntegrationSummary> = {}) {
  const mounted = await mountWithPlugins(IntegrationCard, {
    props: { integration: summary(overrides) },
  })
  const text = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`).text()
  return { ...mounted, text }
}

describe('IntegrationCard', () => {
  it('names the integration, what it provides and how it is', async () => {
    const { text } = await show({ name: 'ntopng', status: 'connected' })
    expect(text('integration-name')).toBe('ntopng')
    expect(text('integration-provides')).toBe('Who talks to whom on the network.')
    expect(text('status')).toBe('Connected')
  })

  it('is a link to the integration’s own page', async () => {
    const { wrapper, router } = await show({ key: 'wazuh' })
    const link = wrapper.find('a')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/integrations/wazuh')
    expect(router.resolve({ name: 'integration', params: { key: 'wazuh' } }).href).toBe(
      '/integrations/wazuh',
    )
  })

  it('says so when it is not connected, and has no call to report', async () => {
    const { text } = await show()
    expect(text('status')).toBe('Not connected')
    expect(text('integration-last-call')).toBe('Not set up yet')
  })

  it('says Set up for one that is not connected, and Manage for the rest', async () => {
    const fresh = await show()
    expect(fresh.wrapper.find('.integration-card__action').text()).toBe('Set up')
    const connected = await show({ status: 'connected' })
    expect(connected.wrapper.find('.integration-card__action').text()).toBe('Manage')
  })

  it('says when the last successful call was, and the exact time on hover', async () => {
    const when = new Date(Date.now() - 5 * 60 * 1000).toISOString()
    const { wrapper, text } = await show({ status: 'connected', last_success_at: when })
    expect(text('integration-last-call')).toBe('Last successful call 5 minutes ago')
    const time = wrapper.find('time')
    expect(time.attributes('datetime')).toBe(when)
    expect(time.attributes('title')).toMatch(/\d{4}/)
  })

  it('says so when it has never worked', async () => {
    const { text } = await show({ status: 'problem' })
    expect(text('integration-last-call')).toBe('No successful call yet')
  })

  it('lists the services that were found', async () => {
    const { wrapper } = await show({
      status: 'connected',
      services: [
        { key: 'suricata', label: 'Suricata', state: 'running' },
        { key: 'crowdsec', label: 'CrowdSec', state: 'installed' },
      ],
    })
    const list = wrapper.find('[data-test="integration-services"]')
    expect(list.attributes('aria-label')).toBe('Services found')
    expect(wrapper.findAll('[data-test="integration-service"]').map((item) => item.text())).toEqual(
      ['Suricata', 'CrowdSec'],
    )
  })

  it('has no list of services when none were found', async () => {
    const { wrapper } = await show()
    expect(wrapper.find('[data-test="integration-services"]').exists()).toBe(false)
  })
})
