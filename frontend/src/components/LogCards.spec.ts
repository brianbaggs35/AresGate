import LogCards from '@/components/LogCards.vue'
import { mountWithPlugins } from '@/test/mount'
import { logEvent } from '@/test/logs'

const NOW = new Date(2026, 9, 27, 9, 0, 0).getTime()
const events = [
  logEvent({
    id: 2,
    at: new Date(2026, 9, 27, 8, 30).toISOString(),
    severity: 'high',
    summary: 'Failed password for root',
  }),
  logEvent({
    id: 1,
    at: new Date(2026, 9, 25, 8, 30).toISOString(),
    source: 'ntopng',
    source_name: 'ntopng',
    kind: 'flow',
    src_address: null,
    src_port: null,
    dst_address: null,
    dst_port: null,
  }),
]

async function open(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(LogCards, {
    props: { events, selected: null, now: NOW, ...props },
  })
  const cards = () => mounted.wrapper.findAll('[data-test="log-card"]')
  return { ...mounted, cards }
}

describe('LogCards', () => {
  it('has a card for each event: how serious, who said it, when, what, and where it went', async () => {
    const { cards } = await open()
    const first = cards()[0]

    expect(cards()).toHaveLength(2)
    expect(first?.find('.log-card__severity').text()).toBe('High')
    expect(first?.find('.log-card__severity svg').exists()).toBe(true)
    expect(first?.find('[data-test="log-card-source"]').text()).toBe('OPNsense · firewall')
    expect(first?.find('time').text()).toBe('30 minutes ago')
    expect(first?.find('time').attributes('datetime')).toBe(events[0]?.at)
    expect(first?.find('time').attributes('title')).toMatch(/Oct 27, 2026.*8:30:00/)
    expect(first?.find('.log-card__summary').text()).toBe('Failed password for root')
    expect(first?.find('[data-test="log-card-route"]').text()).toBe(
      '93.184.216.34:51514 → 192.168.1.20:22',
    )
    expect(first?.attributes('style')).toContain('--accent: rgb(var(--v-theme-error))')
  })

  it('leaves out the route of an event that names no address', async () => {
    const { cards } = await open()

    expect(cards()[1]?.find('[data-test="log-card-route"]').exists()).toBe(false)
    expect(cards()[1]?.find('time').text()).toBe('2 days ago')
  })

  it('says which event is open', async () => {
    const { cards } = await open({ selected: events[1]?.cursor })

    expect(cards()[1]?.attributes('aria-current')).toBe('true')
    expect(cards()[1]?.classes()).toContain('log-card--on')
    expect(cards()[0]?.attributes('aria-current')).toBeUndefined()
  })

  it('opens an event when its card is tapped', async () => {
    const { cards, wrapper } = await open()

    await cards()[1]?.trigger('click')

    expect(wrapper.emitted('open')).toEqual([[events[1]]])
  })

  it('is an empty list for no events', async () => {
    const { cards, wrapper } = await open({ events: [] })

    expect(cards()).toHaveLength(0)
    expect(wrapper.find('ul').exists()).toBe(true)
  })
})
