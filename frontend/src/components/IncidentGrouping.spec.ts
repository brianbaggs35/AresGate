import IncidentGrouping from '@/components/IncidentGrouping.vue'
import { mountWithPlugins } from '@/test/mount'

const LINES = [
  'Signals from 3 addresses of 93.184.216.0/24 doing the same thing are grouped: a bot spread over a block is one actor.',
  'It came in 2 waves: 6 signals in bursts with at least 15 minutes of quiet between them.',
]

async function show(props: { grouping?: string[]; ports?: number[]; capped?: boolean } = {}) {
  const mounted = await mountWithPlugins(IncidentGrouping, {
    props: { grouping: LINES, ports: [], capped: false, ...props },
    withApp: true,
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const ports = () => mounted.wrapper.findAll('[data-test="port"]').map((port) => port.text())
  return { ...mounted, find, ports }
}

describe('IncidentGrouping', () => {
  it('says why the signals are one incident, a fact to a line', async () => {
    const { wrapper } = await show()

    expect(wrapper.findAll('[data-test="grouping-line"]').map((line) => line.text())).toEqual(LINES)
  })

  it('lists the ports it touched, naming the services people know', async () => {
    const { find, ports } = await show({ ports: [22, 80, 8888] })

    expect(find('ports-title').text()).toBe('The 3 ports it touched')
    expect(ports()).toEqual(['22 (SSH)', '80 (HTTP)', '8888'])
  })

  it('lists none when it touched only the one, which the timeline shows', async () => {
    const { find } = await show({ ports: [22] })

    expect(find('ports').exists()).toBe(false)
    expect(find('ports-title').exists()).toBe(false)
  })

  it('lists a couple of dozen of a sweep, and the rest when asked', async () => {
    const { find, ports } = await show({ ports: Array.from({ length: 100 }, (_, i) => i + 1) })

    expect(ports()).toHaveLength(24)
    expect(find('ports-show-more').text()).toBe('Show 48 more')

    await find('ports-show-more').trigger('click')
    expect(ports()).toHaveLength(72)
    expect(find('ports-show-more').text()).toBe('Show 28 more')

    await find('ports-show-more').trigger('click')
    expect(ports()).toHaveLength(100)
    expect(find('ports-show-more').exists()).toBe(false)
  })

  it('says only the first were kept when there were more than it can hold', async () => {
    const { find } = await show({ ports: [1, 2, 3], capped: true })

    expect(find('ports-title').text()).toBe('The first 3 ports it touched')
  })
})
