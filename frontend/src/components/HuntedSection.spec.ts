import type { Hunted } from '@/api/threats'
import HuntedSection from '@/components/HuntedSection.vue'
import { mountWithPlugins } from '@/test/mount'

const item = (changes: Partial<Hunted> = {}): Hunted => ({
  id: 4,
  title: 'Scan from 203.0.113.7',
  severity: 'high',
  agent_id: 3,
  agent_name: 'Night watch',
  run_id: 9,
  finding: 'A scan got further than usual',
  action: 'Close port 22.',
  ...changes,
})

async function open(total: number, items: Hunted[]) {
  return mountWithPlugins(HuntedSection, { props: { hunted: { total, items } } })
}

describe('HuntedSection', () => {
  it('says how many the threat hunter flagged and what it said of each', async () => {
    const { wrapper } = await open(5, [item(), item({ id: 5, severity: 'mysterious', action: '' })])

    expect(wrapper.find('[data-test="hunted"]').text()).toContain(
      'The threat hunter flagged 5 incidents',
    )
    const rows = wrapper.findAll('[data-test="hunted-item"]')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.find('[data-test="severity"]').text()).toBe('High')
    expect(rows[0]!.find('[data-test="hunted-open"]').attributes('href')).toBe('/incidents/4')
    expect(rows[0]!.find('[data-test="hunted-finding"]').text()).toBe(
      'Night watch: A scan got further than usual',
    )
    expect(rows[0]!.find('[data-test="hunted-action"]').text()).toBe('What to do: Close port 22.')
    expect(rows[1]!.find('[data-test="severity"]').text()).toBe('Info')
    expect(rows[1]!.find('[data-test="hunted-action"]').exists()).toBe(false)
  })

  it('leads to every incident it flagged', async () => {
    const { wrapper } = await open(1, [item()])

    expect(wrapper.find('[data-test="hunted"]').text()).toContain('flagged 1 incident')
    expect(wrapper.find('[data-test="hunted-all"]').attributes('href')).toBe(
      '/incidents?q=hunted:yes',
    )
  })

  it('is left out when it flagged nothing', async () => {
    const { wrapper } = await open(0, [])

    expect(wrapper.find('[data-test="hunted"]').exists()).toBe(false)
  })
})
