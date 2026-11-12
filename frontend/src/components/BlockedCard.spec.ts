import BlockedCard from '@/components/BlockedCard.vue'
import { dashboard } from '@/test/dashboard'
import { mountWithPlugins } from '@/test/mount'

const blocked = {
  ...dashboard().blocked,
  total: 1_251,
  inbound: 1_200,
  outbound: 50,
  inside: 1,
  top_ports: [
    { port: 22, service: 'SSH', count: 700 },
    { port: 8080, service: null, count: 1 },
  ],
  top_devices: [
    { address: '192.168.1.20', count: 49, destinations: 3 },
    { address: '192.168.1.21', count: 1, destinations: 1 },
  ],
}

async function open(changes: Partial<typeof blocked> = {}) {
  const mounted = await mountWithPlugins(BlockedCard, {
    signedIn: 'admin',
    withApp: true,
    props: {
      blocked: { ...blocked, ...changes },
      window: '24h',
      lastWords: 'the last 24 hours',
    },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find, text: (selector: string) => find(selector).text() }
}

describe('BlockedCard', () => {
  it('says what it is for and what the blocks were', async () => {
    const { wrapper, text } = await open()

    expect(wrapper.find('h2').text()).toBe('Which way the blocks went')
    expect(text('section-description')).toBe(
      'The connections the firewall refused in the last 24 hours, by where they were going.',
    )
    expect(text('blocked-summary')).toContain('1,200 came from the internet')
    expect(text('blocked-summary')).toContain('50 connections from your own devices')
  })

  it('counts each way and draws only the ways there were', async () => {
    const { find, wrapper } = await open({ inside: 0 })

    expect(find('blocked-inbound').text()).toContain('1,200')
    expect(find('blocked-outbound').text()).toContain('50')
    expect(find('blocked-inside').text()).toContain('0')
    expect(wrapper.findAll('[data-test="blocked-segment"]')).toHaveLength(2)
  })

  it('lists the devices that were turned away and the ports tried, each with the log', async () => {
    const { wrapper, find } = await open()

    const devices = wrapper.findAll('[data-test="blocked-device"]')
    expect(devices).toHaveLength(2)
    expect(devices[0]?.text()).toContain('192.168.1.20')
    expect(devices[0]?.text()).toContain('49 times, to 3 addresses')
    expect(devices[1]?.text()).toContain('1 time, to 1 address')
    expect(find('blocked-device-logs').attributes('href')).toBe(
      '/logs?q=kind:firewall+severity%3E=low+from:192.168.1.20+since:24h',
    )

    const ports = wrapper.findAll('[data-test="blocked-port"]')
    expect(ports.map((port) => port.find('.blocked__name').text())).toEqual(['22 · SSH', '8080'])
    expect(ports[0]?.text()).toContain('700 times')
    expect(ports[1]?.text()).toContain('1 time')
    expect(find('blocked-port-logs').attributes('href')).toContain('port:22')
  })

  it('leaves a list out when it has nothing in it', async () => {
    const { find } = await open({ top_devices: [], top_ports: [] })

    expect(find('blocked-devices').exists()).toBe(false)
    expect(find('blocked-ports').exists()).toBe(false)
  })
})
