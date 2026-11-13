import DeviceCard from '@/components/DeviceCard.vue'
import { identity } from '@/test/assets'
import { device, deviceAsset, standing, yours } from '@/test/devices'
import { mountWithPlugins } from '@/test/mount'

async function open(item = device()) {
  const { wrapper } = await mountWithPlugins(DeviceCard, { props: { device: item }, withApp: true })
  const find = (selector: string) => wrapper.find(`[data-test="${selector}"]`)
  return { wrapper, find, text: (selector: string) => find(selector).text() }
}

describe('DeviceCard', () => {
  it('names the address, links its page and says whose it is', async () => {
    const { find, text } = await open()

    expect(text('device-address')).toBe('52.1.2.3')
    expect(find('device-link').attributes('href')).toBe('/devices/52.1.2.3')
    expect(text('device-scope')).toBe('On the Internet')
    expect(text('device-when')).toMatch(/^Seen /)
  })

  it('says what it is called when it has a name', async () => {
    const { text, find } = await open(device({ name: 'example.test' }))

    expect(text('device-name')).toBe('example.test')
    expect((await open()).find('device-name').exists()).toBe(false)
    expect(find('device-asset').exists()).toBe(false)
  })

  it('counts the connections each way, and says so for none', async () => {
    const { text, wrapper } = await open(device({ incoming: 1234, outgoing: 5 }))

    expect(text('device-incoming')).toContain('1,234 in')
    expect(text('device-outgoing')).toContain('5 out')
    expect(wrapper.text()).not.toContain('No connections this week')
    const quiet = await open(device({ incoming: 0, outgoing: 0 }))
    expect(quiet.wrapper.text()).toContain('No connections this week')
  })

  it('draws the share made to it as a bar, which says it in words', async () => {
    const { wrapper } = await open(device({ incoming: 3, outgoing: 1 }))

    const bar = wrapper.find('[role="img"]')
    expect(bar.attributes('aria-label')).toBe('3 connections to it, 1 from it')
    expect(wrapper.find('.device__in').attributes('style')).toContain('75%')
  })

  it('lists the ports used, with the service each stands for', async () => {
    const { text } = await open()

    expect(text('device-ports')).toContain('443/tcp')
  })

  it('has no ports to list when none were used', async () => {
    const { find } = await open(device({ ports: [], protocols: [] }))

    expect(find('device-ports').exists()).toBe(false)
  })

  it('says how many incidents it is in', async () => {
    const one = await open(device({ incidents: { count: 1, worst: 'high' } }))
    const many = await open(device({ incidents: { count: 3, worst: 'high' } }))

    expect(one.text('device-incidents')).toBe('In 1 incident')
    expect(many.text('device-incidents')).toBe('In 3 incidents')
    expect((await open()).find('device-incidents').exists()).toBe(false)
  })

  it('says what threat intelligence kept of it', async () => {
    const { find } = await open(device({ standing: standing() }))

    expect(find('device-standing').text()).toBe('Malicious')
    expect(find('device-standing').attributes('data-judgement')).toBe('malicious')
  })

  it('links the asset a home address is, and says what Fingerbank says it is', async () => {
    const { find, text } = await open(
      yours({ asset: deviceAsset({ identity: identity({ name: 'Apple iPhone 16' }) }) }),
    )

    expect(find('device-asset').find('a').attributes('href')).toBe('/assets/device-1')
    expect(text('device-asset')).toBe('Laptop')
    expect(text('device-identified')).toBe('Apple iPhone 16')
  })

  it('names the maker when Fingerbank found no name, and says nothing when it found nothing', async () => {
    const maker = await open(
      yours({
        asset: deviceAsset({ identity: identity({ name: null, manufacturer: 'Apple, Inc.' }) }),
      }),
    )
    const unknown = await open(
      yours({ asset: deviceAsset({ identity: identity({ state: 'unknown' }) }) }),
    )

    expect(maker.text('device-identified')).toBe('Apple, Inc.')
    expect(unknown.find('device-identified').exists()).toBe(false)
  })
})
