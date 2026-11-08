import IncidentOccurrences from '@/components/IncidentOccurrences.vue'
import { mountWithPlugins } from '@/test/mount'
import { signal } from '@/test/incidents'

const LAST = new Date(Date.now() - 5 * 60_000).toISOString()

function occurrence(count: number, duplicates = 0, summary = 'ET SCAN Potential SSH Scan') {
  return { signal: signal({ summary }), count, last_at: LAST, duplicates }
}

async function show(occurrences = [occurrence(412, 100)]) {
  const mounted = await mountWithPlugins(IncidentOccurrences, { props: { occurrences } })
  return { ...mounted, items: mounted.wrapper.findAll('[data-test="occurrence"]') }
}

describe('IncidentOccurrences', () => {
  it('says how many times an alert happened, from whom, and when last', async () => {
    const { items } = await show()

    expect(items).toHaveLength(1)
    expect(items[0]?.find('[data-test="occurrence-summary"]').text()).toBe(
      'ET SCAN Potential SSH Scan',
    )
    expect(items[0]?.find('[data-test="occurrence-count"]').text()).toBe('412')
    expect(items[0]?.text()).toContain('times from Wazuh, the last')
    expect(items[0]?.find('[data-test="occurrence-duplicates"]').text()).toBe(
      '100 also reported by another program, counted once.',
    )
  })

  it('leaves out what only happened once and was reported by one program', async () => {
    const { items } = await show([
      occurrence(1),
      occurrence(2, 0, 'Repeated'),
      occurrence(1, 1, 'Twice'),
    ])

    expect(items.map((item) => item.find('[data-test="occurrence-summary"]').text())).toEqual([
      'Repeated',
      'Twice',
    ])
    expect(items[1]?.text()).toContain('1 time from')
  })

  it('lists the most and counts the rest', async () => {
    const many = Array.from({ length: 10 }, (_, index) => occurrence(2, 0, `Alert ${index}`))
    const { items, wrapper } = await show(many)

    expect(items).toHaveLength(8)
    expect(wrapper.find('[data-test="occurrences-more"]').text()).toBe('And 2 more that repeated.')
  })
})
