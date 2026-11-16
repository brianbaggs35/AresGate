import FlowDetail from '@/components/FlowDetail.vue'
import { flow, node } from '@/test/flow'
import { mountWithPlugins } from '@/test/mount'

async function open(picked = node({ events: 7, blocked: 1 }), hours: 1 | 6 | 24 | 168 = 24) {
  const mounted = await mountWithPlugins(FlowDetail, {
    withApp: true,
    signedIn: 'admin',
    route: '/flow',
    props: { flow: flow(), node: picked, hours },
  })
  const text = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`).text()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, text, find }
}

describe('FlowDetail', () => {
  it('says what the block is and how much of it was refused', async () => {
    const { text, wrapper } = await open()

    expect(text('detail-name')).toBe('192.168.1.20')
    expect(text('detail-events')).toBe('7')
    expect(text('detail-blocked')).toBe('1 (14%)')
    expect(text('detail-scope')).toBe('On your network')
    expect(wrapper.text()).toContain('Who connected')
  })

  it('says what it is joined to, the biggest first', async () => {
    const { wrapper } = await open()

    const items = wrapper.findAll('[data-test="detail-joined"] li').map((item) => item.text())

    expect(items).toEqual(['tcp/443 (HTTPS)6', 'tcp/25 (SMTP)1, 1 refused'])
    expect(wrapper.text()).toContain('Connected')
  })

  it('names a service by who used it, and has no device for it', async () => {
    const { wrapper, find } = await open(
      node({
        id: 'service:tcp/443',
        column: 'service',
        label: 'tcp/443',
        scope: null,
        protocol: 'tcp',
        port: 443,
        events: 6,
      }),
    )

    expect(wrapper.text()).toContain('Used by')
    expect(find('detail-scope').exists()).toBe(false)
    expect(find('detail-device').exists()).toBe(false)
    expect(find('detail-logs').attributes('href')).toBe(
      '/logs?q=kind:firewall+since:24h+protocol:tcp+port:443',
    )
  })

  it('leads to the logs of an address and to its device', async () => {
    const { find } = await open(
      node({
        id: 'destination:8.8.8.8',
        column: 'destination',
        label: '8.8.8.8',
        scope: 'outside',
        name: 'dns.example.net',
        events: 4,
      }),
      168,
    )

    expect(find('detail-logs').attributes('href')).toBe('/logs?q=kind:firewall+since:7d+to:8.8.8.8')
    expect(find('detail-device').attributes('href')).toBe('/devices/8.8.8.8')
    expect(find('detail-host').text()).toBe('dns.example.net')
    expect(find('detail-scope').text()).toBe('On the Internet')
  })

  it('has nothing to read or open for the others folded together', async () => {
    const { find } = await open(
      node({ id: 'source:others', label: 'Others', scope: null, folded: 4, events: 9 }),
    )

    expect(find('detail-name').text()).toBe('4 others')
    expect(find('detail-logs').exists()).toBe(false)
    expect(find('detail-device').exists()).toBe(false)
    expect(find('detail-host').exists()).toBe(false)
  })

  it('has no list of what it is joined to when it is joined to nothing', async () => {
    const { find } = await open(node({ id: 'source:nobody', label: '9.9.9.9' }))

    expect(find('detail-joined').exists()).toBe(false)
  })

  it('can be closed', async () => {
    const { find, wrapper } = await open()

    await find('detail-close').trigger('click')

    expect(wrapper.findComponent(FlowDetail).emitted('close')).toHaveLength(1)
  })
})
