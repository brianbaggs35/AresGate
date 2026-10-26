import IncidentTimeline from '@/components/IncidentTimeline.vue'
import { signal } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

const DAY = 24 * 3_600_000
const AT = Date.parse('2026-10-26T14:00:00Z')

async function show(
  signals = [signal({ occurred_at: new Date(AT).toISOString() })],
  total?: number,
) {
  const mounted = await mountWithPlugins(IncidentTimeline, {
    props: { signals, total: total ?? signals.length },
    withApp: true,
  })
  const rows = () => mounted.wrapper.findAll('[data-test="signal"]')
  return { ...mounted, rows }
}

describe('IncidentTimeline', () => {
  it('lists each signal with who reported it, how serious they thought it was and what they said', async () => {
    const { rows } = await show([
      signal({ occurred_at: new Date(AT).toISOString() }),
      signal({
        occurred_at: new Date(AT + 60_000).toISOString(),
        source_name: 'OPNsense',
        severity: 'low',
        summary: 'Blocked',
      }),
    ])

    expect(rows()).toHaveLength(2)
    expect(rows()[0]?.find('[data-test="signal-source"]').text()).toBe('Wazuh')
    expect(rows()[0]?.find('[data-test="severity"]').text()).toBe('High')
    expect(rows()[0]?.find('[data-test="signal-summary"]').text()).toBe(
      'sshd: authentication failed',
    )
    expect(rows()[1]?.find('[data-test="signal-source"]').text()).toBe('OPNsense')
    expect(rows()[1]?.find('[data-test="severity"]').text()).toBe('Low')
  })

  it('gives the time down to the second, machine-readable', async () => {
    const { rows } = await show()

    const time = rows()[0]?.find('[data-test="signal-time"]')
    expect(time?.text()).toMatch(/\d{1,2}:\d{2}:\d{2}/)
    expect(time?.attributes('datetime')).toBe('2026-10-26T14:00:00.000Z')
  })

  it('says the day only where it changes', async () => {
    const { rows } = await show([
      signal({ occurred_at: new Date(AT).toISOString() }),
      signal({ occurred_at: new Date(AT + 60_000).toISOString() }),
      signal({ occurred_at: new Date(AT + 2 * DAY).toISOString() }),
    ])

    expect(rows().map((row) => row.find('[data-test="signal-day"]').exists())).toEqual([
      true,
      false,
      true,
    ])
  })

  it('shows what the program called it, when that is not what it said', async () => {
    const { rows } = await show([
      signal({ signature: 'Brute force on ssh', summary: 'sshd: authentication failed' }),
      signal({ signature: 'same', summary: 'same' }),
      signal({ signature: null, summary: 'no name' }),
    ])

    expect(rows()[0]?.find('[data-test="signal-name"]').text()).toBe('Brute force on ssh')
    expect(rows()[1]?.find('[data-test="signal-name"]').exists()).toBe(false)
    expect(rows()[2]?.find('[data-test="signal-name"]').exists()).toBe(false)
  })

  it('shows the traffic it was about, if it named any', async () => {
    const { rows } = await show([
      signal(),
      signal({ src_address: null, dst_address: null, src_port: null, dst_port: null }),
    ])

    expect(rows()[0]?.find('[data-test="signal-flow"]').text()).toBe(
      '93.184.216.34:51514 → 192.168.1.20:22 (tcp)',
    )
    expect(rows()[1]?.find('[data-test="signal-flow"]').exists()).toBe(false)
  })

  it('marks a ban, which is not an alert', async () => {
    const { rows } = await show([signal(), signal({ kind: 'decision', source_name: 'CrowdSec' })])

    expect(rows()[0]?.find('[data-test="signal-ban"]').exists()).toBe(false)
    expect(rows()[1]?.find('[data-test="signal-ban"]').text()).toBe('Ban')
  })

  it('colors the dot by how serious the signal is', async () => {
    const { rows } = await show([signal({ severity: 'critical' })])

    expect(rows()[0]?.attributes('style')).toContain('rgb(var(--v-theme-error))')
  })

  it('says how many were left out when there are more than are listed', async () => {
    const { wrapper } = await show([signal(), signal()], 1_500)

    expect(wrapper.find('[data-test="timeline-more"]').text()).toBe(
      'Only the first 2 of its 1,500 signals are kept. The rest are counted, but not listed.',
    )
  })

  it('says nothing about that when they are all listed', async () => {
    const { wrapper } = await show([signal(), signal()])

    expect(wrapper.find('[data-test="timeline-more"]').exists()).toBe(false)
  })

  describe('when there are a lot of signals', () => {
    const many = (count: number) =>
      Array.from({ length: count }, (_, index) =>
        signal({ occurred_at: new Date(AT + index * 1_000).toISOString() }),
      )

    it('lists the first twenty-five, and offers the rest', async () => {
      const { rows, wrapper } = await show(many(60))

      expect(rows()).toHaveLength(25)
      expect(wrapper.find('[data-test="timeline-show-more"]').text()).toBe('Show 25 more')
    })

    it('lists another twenty-five each time it is asked', async () => {
      const { rows, wrapper } = await show(many(60))

      await wrapper.find('[data-test="timeline-show-more"]').trigger('click')
      expect(rows()).toHaveLength(50)
      expect(wrapper.find('[data-test="timeline-show-more"]').text()).toBe('Show 10 more')

      await wrapper.find('[data-test="timeline-show-more"]').trigger('click')
      expect(rows()).toHaveLength(60)
      expect(wrapper.find('[data-test="timeline-show-more"]').exists()).toBe(false)
    })

    it('offers nothing when all fit on the first page', async () => {
      const { wrapper } = await show(many(25))

      expect(wrapper.find('[data-test="timeline-show-more"]').exists()).toBe(false)
    })
  })
})
