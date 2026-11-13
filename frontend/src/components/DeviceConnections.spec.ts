import DeviceConnections from '@/components/DeviceConnections.vue'
import { connection } from '@/test/devices'
import { mountWithPlugins } from '@/test/mount'

async function open(connections = [connection()]) {
  const { wrapper } = await mountWithPlugins(DeviceConnections, {
    props: { connections },
    withApp: true,
  })
  return wrapper
}

describe('DeviceConnections', () => {
  it('says which way each went, from where to where, over which port, how often and when', async () => {
    const wrapper = await open([
      connection(),
      connection({ direction: 'incoming', peer: '52.1.2.4', port: 22, events: 1 }),
    ])
    const rows = wrapper.findAll('[data-test="connection"]')

    expect(rows).toHaveLength(2)
    const [out, incoming] = rows
    expect(out?.find('[data-test="connection-direction"]').text()).toBe('Connected out')
    expect(out?.find('[data-test="connection-source"]').text()).toBe('This device')
    expect(out?.find('[data-test="connection-destination"]').text()).toBe('52.1.2.3')
    expect(out?.find('[data-test="connection-port"]').text()).toContain('443/tcp')
    expect(out?.find('[data-test="connection-seen"]').text()).toContain('3 times')
    expect(incoming?.find('[data-test="connection-direction"]').text()).toBe('Connected to')
    expect(incoming?.find('[data-test="connection-source"]').text()).toBe('52.1.2.4')
    expect(incoming?.find('[data-test="connection-destination"]').text()).toBe('This device')
    expect(incoming?.find('[data-test="connection-seen"]').text()).toContain('1 time,')
  })

  it('links the other end to its own page', async () => {
    const wrapper = await open()

    expect(wrapper.find('[data-test="connection-peer"]').attributes('href')).toBe(
      '/devices/52.1.2.3',
    )
  })

  it('says when the other end is not known', async () => {
    const wrapper = await open([
      connection({ peer: null }),
      connection({ direction: 'incoming', peer: null }),
    ])

    expect(wrapper.findAll('[data-test="connection-peer"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('Unknown address')
  })

  it('says the port when only a protocol was said, and when there is neither', async () => {
    const wrapper = await open([
      connection({ port: null, protocol: 'icmp' }),
      connection({ port: null, protocol: null }),
    ])
    const ports = wrapper.findAll('[data-test="connection-port"]').map((port) => port.text())

    expect(ports[0]).toContain('icmp')
    expect(ports[1]).toContain('Not said')
  })
})
