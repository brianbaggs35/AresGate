import IncidentReasons from '@/components/IncidentReasons.vue'
import { reason } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

const reasons = [
  reason(),
  reason({ rule: 'corroborated', points: 15, text: '2 programs saw it: OPNsense and Wazuh.' }),
  reason({ rule: 'repeated', points: 10, text: 'It has set off 5 signals.' }),
]

async function show(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(IncidentReasons, {
    props: { reasons, confidence: 65, level: 'high', ...props },
  })
  const rows = () => mounted.wrapper.findAll('[data-test="reason"]')
  return { ...mounted, rows }
}

describe('IncidentReasons', () => {
  it('leads with how sure AresGate is', async () => {
    const { wrapper } = await show()

    expect(wrapper.find('[data-test="confidence-level"]').text()).toBe('High confidence')
    expect(wrapper.find('[data-test="confidence-value"]').text()).toBe('65 of 100')
  })

  it('lists each reason with its name, what it saw and its points', async () => {
    const { rows } = await show()

    expect(rows().map((row) => row.find('[data-test="reason-label"]').text())).toEqual([
      'Most serious signal',
      'Other programs agree',
      'It keeps happening',
    ])
    expect(rows().map((row) => row.find('[data-test="reason-points"]').text())).toEqual([
      '+40',
      '+15',
      '+10',
    ])
    expect(rows()[1]?.find('[data-test="reason-text"]').text()).toBe(
      '2 programs saw it: OPNsense and Wazuh.',
    )
  })

  it('adds the points up', async () => {
    const { wrapper } = await show()

    expect(wrapper.find('[data-test="reasons-total"]').text()).toBe('65 points.')
  })

  it('draws a bar of how much of the 100 each reason is, in the same colors as its list', async () => {
    const { wrapper } = await show()

    const widths = wrapper
      .findAll('.reasons__segment')
      .map((segment) => segment.attributes('style') ?? '')
    expect(widths).toHaveLength(3)
    expect(widths[0]).toContain('width: 40%')
    expect(widths[1]).toContain('width: 15%')
    expect(widths[2]).toContain('width: 10%')
    const swatches = wrapper.findAll('.reasons__swatch').map((item) => item.attributes('style'))
    expect(swatches[0]).toContain('var(--chart-1)')
    expect(widths[0]).toContain('var(--chart-1)')
    expect(swatches[2]).toContain('var(--chart-3)')
    expect(wrapper.find('[data-test="reasons-bar"]').attributes('aria-hidden')).toBe('true')
  })

  it('says when the points came to more than the most there is', async () => {
    const { wrapper } = await show({
      reasons: [...reasons, reason({ rule: 'banned', points: 50, text: 'A program banned it.' })],
      confidence: 100,
    })

    expect(wrapper.find('[data-test="reasons-total"]').text()).toBe(
      '115 points, counted as 100, the most there is.',
    )
    const widths = wrapper.findAll('.reasons__segment').map((item) => item.attributes('style'))
    // Shares of the 115 that were added up, so the bar never runs over.
    expect(widths[0]).toContain('34.78')
  })

  it('leaves a reason that adds nothing out of the bar, but not out of the list', async () => {
    const { wrapper, rows } = await show({
      reasons: [reason({ rule: 'strongest', points: 0, text: 'Rated info.' }), ...reasons],
    })

    expect(rows()).toHaveLength(4)
    expect(wrapper.findAll('.reasons__segment')).toHaveLength(3)
  })

  it('calls a reason this version does not know by its key', async () => {
    const { rows } = await show({
      reasons: [reason({ rule: 'geography', points: 5, text: 'It came from far away.' })],
    })

    expect(rows()[0]?.find('[data-test="reason-label"]').text()).toBe('geography')
  })
})
