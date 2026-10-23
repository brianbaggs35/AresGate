import type { Part } from '@/api/status'
import PartList from '@/components/PartList.vue'
import { mountWithPlugins } from '@/test/mount'

const HOUR = 3_600_000

function part(changes: Partial<Part> = {}): Part {
  return {
    key: 'wazuh',
    name: 'Wazuh',
    group: 'integration',
    state: 'ok',
    detail: null,
    last_success_at: null,
    integration: 'wazuh',
    ...changes,
  }
}

async function show(parts: Part[]) {
  const { wrapper } = await mountWithPlugins(PartList, { props: { parts } })
  const texts = (selector: string) =>
    wrapper.findAll(`[data-test="${selector}"]`).map((item) => item.text())
  return { wrapper, texts }
}

describe('PartList', () => {
  it.each([
    ['ok', 'Working'],
    ['problem', 'Problem'],
    ['unknown', 'Not tested yet'],
    ['off', 'Off'],
  ] as const)('says an integration in the state %s is "%s"', async (state, label) => {
    const { texts } = await show([part({ state })])
    expect(texts('part-state')).toEqual([label])
  })

  it('says a collector that has not run yet is waiting, and not that it is untested', async () => {
    const { texts } = await show([part({ group: 'collector', state: 'unknown' })])
    expect(texts('part-state')).toEqual(['Waiting'])
  })

  it.each([
    ['ok', 'Working'],
    ['problem', 'Problem'],
    ['off', 'Off'],
  ] as const)('says a collector in the state %s is "%s"', async (state, label) => {
    const { texts } = await show([part({ group: 'collector', state })])
    expect(texts('part-state')).toEqual([label])
  })

  it('shows why a part has a problem, and when it last worked', async () => {
    const { texts } = await show([
      part({
        state: 'problem',
        detail: 'The certificate was refused.',
        last_success_at: new Date(Date.now() - 3 * HOUR).toISOString(),
      }),
    ])
    expect(texts('part-detail')).toEqual(['The certificate was refused. · Last worked 3 hours ago'])
  })

  it('says nothing about a part that has nothing to say', async () => {
    const { wrapper } = await show([part()])
    expect(wrapper.find('[data-test="part-name"]').text()).toBe('Wazuh')
    expect(wrapper.find('[data-test="part-detail"]').exists()).toBe(false)
  })

  it('leads to the page of the integration a part belongs to, when it has one', async () => {
    const { wrapper } = await show([
      part(),
      part({ key: 'worker', name: 'Collector worker', group: 'collector', integration: null }),
    ])
    const links = wrapper.findAll('[data-test="part-open"]')
    expect(links).toHaveLength(1)
    expect(links[0]?.attributes('href')).toBe('/integrations/wazuh')
    expect(links[0]?.attributes('aria-label')).toBe('Open Wazuh')
  })
})
