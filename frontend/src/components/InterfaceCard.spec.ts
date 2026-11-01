import InterfaceCard from '@/components/InterfaceCard.vue'
import { feed, iface, speed, stats } from '@/test/interfaces'
import { mountWithPlugins } from '@/test/mount'

const WITH_FEEDS = iface({
  id: 7,
  name: 'Internet',
  feeds: [
    feed({ id: 1 }),
    feed({ id: 2, native_name: 'igc1' }),
    feed({ id: 3, integration_name: 'ntopng', integration: 'ntopng' }),
  ],
})

async function open(item = WITH_FEEDS, found: ReturnType<typeof stats> | null = stats()) {
  const mounted = await mountWithPlugins(InterfaceCard, {
    props: { item, stats: found ?? undefined },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('InterfaceCard', () => {
  it('names the interface and what it is for, and opens its page', async () => {
    const { wrapper, find } = await open()

    expect(find('interface-name').text()).toBe('Internet')
    expect(find('interface-role').text()).toBe('Internet')
    expect(wrapper.find('a').attributes('href')).toBe('/interfaces/7')
  })

  it('shows how its traffic has gone and how fast it goes now, in both directions', async () => {
    const { wrapper, find } = await open()

    expect(wrapper.find('[data-test="sparkline"]').attributes('aria-label')).toBe(
      'Traffic through Internet in the last 24 hours',
    )
    expect(find('interface-received').text()).toContain('2 Mb/s')
    expect(find('interface-sent').text()).toContain('400 kb/s')
  })

  it('shows what is received when nothing was sent that could be measured', async () => {
    const { find } = await open(
      WITH_FEEDS,
      stats({ speed: speed({ received: [1_000_000], sent: [null] }) }),
    )

    expect(find('interface-received').exists()).toBe(true)
    expect(find('interface-sent').exists()).toBe(false)
  })

  it('says so when nothing has been measured', async () => {
    const { find } = await open(WITH_FEEDS, stats({ speed: null }))
    expect(find('interface-no-traffic').text()).toBe('No traffic measured yet.')
  })

  it('says so when nothing is placed on it yet', async () => {
    const { find, wrapper } = await open(iface(), null)

    expect(find('interface-no-traffic').text()).toBe('Nothing is placed here yet.')
    expect(find('interface-alerts').text()).toBe('0')
    expect(find('interface-devices').text()).toBe('–')
    expect(wrapper.find('[aria-label="Reported by"]').exists()).toBe(false)
  })

  it('counts its alerts, and says how that compares with the day before', async () => {
    const { find, wrapper } = await open()

    expect(find('interface-alerts').text()).toBe('3')
    expect(wrapper.text()).toContain('+2 since the day before')
  })

  it.each([
    [{ alerts: 1, alerts_previous: 4 }, '−3 since the day before'],
    [{ alerts: 2, alerts_previous: 2 }, 'Same as the day before'],
    [{ alerts: 0, alerts_previous: 0 }, 'None in two days'],
  ])('says %j in words', async (counts, words) => {
    const { wrapper } = await open(WITH_FEEDS, stats(counts))
    expect(wrapper.text()).toContain(words)
  })

  it('counts the devices on its networks, or says what is needed to', async () => {
    expect((await open()).find('interface-devices').text()).toBe('12')

    const none = await open(WITH_FEEDS, stats({ devices: null }))
    expect(none.find('interface-devices').text()).toBe('–')
    expect(none.wrapper.text()).toContain('Add its networks to count them')
  })

  it('lists each program that reports about it once', async () => {
    const { wrapper } = await open()

    expect(
      wrapper.findAll('[aria-label="Reported by"] li').map((program) => program.text()),
    ).toEqual(['OPNsense', 'ntopng'])
  })

  it('says when it last reported', async () => {
    const { wrapper } = await open(WITH_FEEDS, stats({ last_seen_at: new Date().toISOString() }))
    expect(wrapper.text()).toContain('Reported')
  })
})
