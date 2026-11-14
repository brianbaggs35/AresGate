import { item } from '@/test/incidentResponse'
import ResponseRow from '@/components/ResponseRow.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(changes: Parameters<typeof item>[0] = {}) {
  const { wrapper } = await mountWithPlugins(ResponseRow, {
    props: { item: item(changes) },
    route: '/incident-response',
  })
  return wrapper
}

describe('ResponseRow', () => {
  it('leads to the incident from its title', async () => {
    const wrapper = await show({ id: 12, title: 'Brute force on ssh' })

    const link = wrapper.find('[data-test="response-link"]')
    expect(link.text()).toBe('Brute force on ssh')
    expect(link.attributes('href')).toBe('/incidents/12')
  })

  it('says how serious it is and what became of it', async () => {
    const wrapper = await show({ severity: 'critical', status: 'investigating' })

    expect(wrapper.find('[data-test="severity"]').text()).toBe('Critical')
    expect(wrapper.find('[data-test="incident-status"]').text()).toBe('Investigating')
  })

  it('says why, for an incident that needs a response', async () => {
    const wrapper = await show({ why: 'It came back after its ban ended.' })

    expect(wrapper.find('[data-test="response-why"]').text()).toBe(
      'It came back after its ban ended.',
    )
    expect(wrapper.find('[data-test="response-answer"]').exists()).toBe(false)
  })

  it('says what was done, for one that does not', async () => {
    const wrapper = await show({ why: null, state: 'blocked', blocked: 3 })

    expect(wrapper.find('[data-test="response-answer"]').text()).toBe(
      'The firewall turned it away 3 times.',
    )
    expect(wrapper.find('[data-test="response-why"]').exists()).toBe(false)
  })

  it('says when it was last seen', async () => {
    const wrapper = await show({ last_seen_at: new Date(Date.now() - 3 * 3600_000).toISOString() })

    expect(wrapper.find('[data-test="response-when"]').text()).toBe('3 hours ago')
  })
})
