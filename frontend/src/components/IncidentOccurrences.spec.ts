import IncidentOccurrences from '@/components/IncidentOccurrences.vue'
import { mountWithPlugins } from '@/test/mount'
import { confirmation, evidence, occurrence as made, signal } from '@/test/incidents'

const LAST = new Date(Date.now() - 5 * 60_000).toISOString()

function occurrence(count: number, duplicates = 0, summary = 'ET SCAN Potential SSH Scan') {
  return made({ signal: signal({ summary }), count, last_at: LAST, duplicates })
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
    // Nothing was said beyond the basics, so there is nothing to open.
    expect(items[0]?.find('[data-test="occurrence-toggle"]').exists()).toBe(false)
  })

  it('names the programs that reported the same alert, and counts it once', async () => {
    const { items } = await show([
      made({
        count: 3,
        duplicates: 4,
        confirmations: [confirmation(), confirmation({ source: 'ntopng', source_name: 'ntopng' })],
      }),
    ])

    expect(items[0]?.find('[data-test="occurrence-duplicates"]').text()).toBe(
      '4 also reported by OPNsense and ntopng, counted once.',
    )
  })

  it('lists an alert that was said once but has more to say', async () => {
    const { items } = await show([made({ evidence: evidence({ host: 'web1' }) })])

    expect(items).toHaveLength(1)
  })

  describe('what each program said', () => {
    const said = made({
      signal: signal({ source: 'wazuh', source_name: 'Wazuh' }),
      evidence: evidence({ host: 'web1' }),
      duplicates: 1,
      confirmations: [
        confirmation({ evidence: evidence({ app: 'ssh' }) }),
        confirmation({ source: 'ntopng', source_name: 'ntopng' }),
      ],
    })

    it('is open for the first alert that has any, with each program that said any', async () => {
      const { items } = await show([said, made({ evidence: evidence({ host: 'other' }) })])

      const reports = items[0]?.findAll('[data-test="occurrence-report"]') ?? []
      // ntopng said nothing, so it is not there to open.
      expect(reports.map((each) => each.find('h3').text())).toEqual(['Wazuh', 'OPNsense'])
      expect(items[0]?.find('[data-test="occurrence-toggle"]').attributes('aria-expanded')).toBe(
        'true',
      )
      expect(items[0]?.find('[data-test="occurrence-reports"]').isVisible()).toBe(true)
      expect(items[1]?.find('[data-test="occurrence-toggle"]').attributes('aria-expanded')).toBe(
        'false',
      )
      expect(items[1]?.find('[data-test="occurrence-reports"]').isVisible()).toBe(false)
    })

    it('opens and closes when asked', async () => {
      const { items } = await show([said, made({ evidence: evidence({ host: 'other' }) })])

      await items[1]?.find('[data-test="occurrence-toggle"]').trigger('click')
      await items[0]?.find('[data-test="occurrence-toggle"]').trigger('click')

      expect(items[1]?.find('[data-test="occurrence-toggle"]').text()).toBe(
        'Hide what the program said',
      )
      expect(items[1]?.find('[data-test="occurrence-reports"]').isVisible()).toBe(true)
      expect(items[0]?.find('[data-test="occurrence-toggle"]').text()).toBe(
        'Show what each program said',
      )
      expect(items[0]?.find('[data-test="occurrence-reports"]').isVisible()).toBe(false)
    })
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
