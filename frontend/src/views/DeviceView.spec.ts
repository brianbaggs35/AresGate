import { ApiError } from '@/api/client'
import * as devicesApi from '@/api/devices'
import AssetEvents from '@/components/AssetEvents.vue'
import AssetIdentity from '@/components/AssetIdentity.vue'
import DeviceConnections from '@/components/DeviceConnections.vue'
import { identity, profile } from '@/test/assets'
import {
  connection,
  device,
  deviceAsset,
  deviceDetail,
  involved,
  standing,
  yours,
} from '@/test/devices'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import DeviceView from '@/views/DeviceView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

interface Options {
  route?: string
  answer?: devicesApi.DeviceDetail | Error
}

async function open({ route = '/devices/52.1.2.3', answer = deviceDetail() }: Options = {}) {
  const fetchDevice = vi.spyOn(devicesApi, 'fetchDevice')
  if (answer instanceof Error) fetchDevice.mockRejectedValue(answer)
  else fetchDevice.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(DeviceView, { signedIn: 'admin', withApp: true, route })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  return { ...mounted, fetchDevice, find, text }
}

describe('DeviceView', () => {
  it('asks for the page of the address the route names', async () => {
    const { fetchDevice } = await open()

    expect(fetchDevice).toHaveBeenCalledWith('52.1.2.3')
  })

  it('shows a skeleton until the answer arrives', async () => {
    vi.spyOn(devicesApi, 'fetchDevice').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(DeviceView, {
      signedIn: 'admin',
      route: '/devices/52.1.2.3',
    })

    expect(wrapper.find('[data-test="device-loading"]').exists()).toBe(true)
  })

  it('names the address, what it is called and whose it is, and leads back to the list', async () => {
    const { wrapper, text } = await open({
      answer: deviceDetail({ device: device({ name: 'example.test' }) }),
    })

    expect(wrapper.find('h1').text()).toBe('52.1.2.3')
    expect(wrapper.find('[data-test="page-description"]').text()).toBe(
      'example.test · On the Internet',
    )
    expect(text('device-scope')).toBe('On the Internet')
  })

  it('says only whose it is when it has no name', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('[data-test="page-description"]').text()).toBe('On the Internet')
  })

  it('counts the connections each way, when it was last seen and the events of the last day', async () => {
    const { text } = await open({
      answer: deviceDetail({ device: device({ incoming: 12, outgoing: 3 }), events_day: 5 }),
    })

    expect(text('device-tile-incoming')).toContain('12')
    expect(text('device-tile-outgoing')).toContain('3')
    expect(text('device-tile-seen')).toContain('Last seen')
    expect(text('device-tile-events')).toContain('5')
    expect(text('device-tile-events')).toContain('4 in the last week')
  })

  it('lists what it connected with', async () => {
    const { wrapper } = await open({
      answer: deviceDetail({ connections: [connection(), connection({ peer: '52.1.2.4' })] }),
    })

    expect(wrapper.findComponent(DeviceConnections).props('connections')).toHaveLength(2)
  })

  it('says when no connection was reported', async () => {
    const { find } = await open({ answer: deviceDetail({ connections: [] }) })

    expect(find('device-no-connections').exists()).toBe(true)
    expect(find('connections').exists()).toBe(false)
  })

  it('lists the events it was in, or says there were none', async () => {
    const some = await open()
    const none = await open({ answer: deviceDetail({ events: [] }) })

    expect(some.wrapper.findComponent(AssetEvents).exists()).toBe(true)
    expect(none.find('device-no-events').exists()).toBe(true)
  })

  describe('the incidents and threats', () => {
    it('say it is in none', async () => {
      const { find } = await open()

      expect(find('device-no-incidents').exists()).toBe(true)
      expect(find('device-incidents').exists()).toBe(false)
    })

    it('link each incident, its kind of threat and its chain, and say how many it is in', async () => {
      const { find, wrapper, text } = await open({
        answer: deviceDetail({
          device: device({ incidents: { count: 2, worst: 'high' } }),
          incidents: [involved(), involved({ id: 8, family_id: null, chain_id: 5 })],
        }),
      })

      expect(text('device-incidents')).toBe('In 2 incidents')
      const links = wrapper.findAll('[data-test="device-incident-link"]')
      expect(links.map((link) => link.attributes('href'))).toEqual(['/incidents/7', '/incidents/8'])
      expect(find('device-family-link').attributes('href')).toBe('/threats/kinds/3')
      expect(find('device-family-link').text()).toBe('Port scan')
      expect(find('device-chain-link').attributes('href')).toBe('/threats/chains/5')
    })

    it('say one incident for one, and call the kind of threat by a name when it has none', async () => {
      const { text, find } = await open({
        answer: deviceDetail({
          device: device({ incidents: { count: 1, worst: 'high' } }),
          incidents: [involved({ family_label: null })],
        }),
      })

      expect(text('device-incidents')).toBe('In 1 incident')
      expect(find('device-family-link').text()).toBe('Kind of threat')
    })
  })

  describe('what threat intelligence says', () => {
    it('is not there when nothing is kept', async () => {
      const { find } = await open()

      expect(find('device-standing-section').exists()).toBe(false)
      expect(find('device-standing').exists()).toBe(false)
    })

    it('says the judgement, how many engines flagged it, who owns it and when it was checked', async () => {
      const { find, text } = await open({
        answer: deviceDetail({ device: device({ standing: standing() }) }),
      })

      expect(find('device-standing').text()).toBe('Malicious')
      const section = text('device-standing-section')
      expect(section).toContain('5 of 70 engines flagged it')
      expect(section).toContain('Example Hosting, NL')
      expect(section).toContain('Checked')
      expect(find('device-ruling').exists()).toBe(false)
    })

    it('says what the owner ruled, which stands over it', async () => {
      const { text } = await open({
        answer: deviceDetail({
          device: device({
            standing: standing({
              ruling: 'safe',
              ruling_note: 'My backup service',
              judgement: 'clean',
            }),
          }),
        }),
      })

      expect(text('device-ruling')).toContain('You ruled it')
      expect(text('device-ruling')).toContain('My backup service')
    })

    it('says no more of a report there is none of', async () => {
      const { text } = await open({
        answer: deviceDetail({
          device: device({
            standing: standing({
              judgement: 'unknown',
              reported: 'unknown',
              owner: null,
              country: null,
              ruling: 'suspicious',
              ruling_note: null,
            }),
          }),
        }),
      })

      const section = text('device-standing-section')
      expect(section).not.toContain('engines flagged')
      expect(text('device-ruling')).toContain('You ruled it')
    })
  })

  describe('a device of the home', () => {
    it('links the asset it is, with its maker and hardware address', async () => {
      const { find, text } = await open({
        route: '/devices/192.168.1.20',
        answer: deviceDetail({ device: yours() }),
      })

      expect(find('device-asset-link').attributes('href')).toBe('/assets/device-1')
      expect(text('device-asset-section')).toContain('Example Devices Inc.')
      expect(text('device-asset-section')).toContain('00:11:22:0a:0b:0c')
      expect(find('device-identity').exists()).toBe(false)
      expect(find('device-asset-kind').exists()).toBe(false)
    })

    it('says what the owner said it is, and what Fingerbank says it is', async () => {
      const { find, text, wrapper } = await open({
        route: '/devices/192.168.1.20',
        answer: deviceDetail({
          device: yours({ asset: deviceAsset({ profile: profile(), identity: identity() }) }),
        }),
      })

      expect(text('device-asset-kind')).toContain('Camera or doorbell')
      expect(text('device-asset-kind')).toContain('Watches the front door')
      expect(wrapper.findComponent(AssetIdentity).props('identity').name).toBe('Apple iPhone 16')
      expect(find('device-identity').exists()).toBe(true)
    })

    it('leaves out a maker, a hardware address and a purpose it has not got', async () => {
      const { text } = await open({
        route: '/devices/192.168.1.20',
        answer: deviceDetail({
          device: yours({
            asset: deviceAsset({
              vendor: null,
              mac: null,
              profile: profile({ purpose: null }),
            }),
          }),
        }),
      })

      expect(text('device-asset-section')).not.toContain('·  ·')
      expect(text('device-asset-kind')).not.toContain('Watches')
    })

    it('has no section for a device that is not one of the home', async () => {
      const { find } = await open()

      expect(find('device-asset-section').exists()).toBe(false)
    })
  })

  describe('when it is not there', () => {
    it('says that nothing is known of the address', async () => {
      const { find } = await open({ answer: new ApiError(404, 'Not found', 'not_found') })

      expect(find('device-missing').text()).toContain('Nothing is known of that address')
      expect(find('device-error').exists()).toBe(false)
    })

    it('says why it cannot load, and tries again', async () => {
      const { find, fetchDevice } = await open({ answer: offline() })

      expect(find('device-error').text()).toContain("Can't reach AresGate.")
      fetchDevice.mockResolvedValue(deviceDetail())

      await find('device-retry').trigger('click')
      await flushPromises()

      expect(find('device-error').exists()).toBe(false)
      expect(find('device-connections').exists()).toBe(true)
    })

    it('keeps what it has when a refresh in the background fails', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { fetchDevice, find } = await open()
        fetchDevice.mockRejectedValue(offline())

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(fetchDevice).toHaveBeenCalledTimes(2)
        expect(find('device-error').exists()).toBe(false)
        expect(find('device-connections').exists()).toBe(true)
      } finally {
        vi.useRealTimers()
      }
    })

    it('finds nothing for a device a refresh in the background no longer finds', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { fetchDevice, find } = await open()
        fetchDevice.mockRejectedValue(new ApiError(404, 'Not found', 'not_found'))

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(find('device-missing').exists()).toBe(true)
      } finally {
        vi.useRealTimers()
      }
    })
  })

  describe('moving to another address', () => {
    it('asks for the new one and shows nothing of the old meanwhile', async () => {
      const { fetchDevice, router, find, wrapper } = await open()
      fetchDevice.mockResolvedValue(deviceDetail({ device: device({ address: '52.1.2.4' }) }))

      await router.push('/devices/52.1.2.4')
      await flushPromises()

      expect(fetchDevice).toHaveBeenLastCalledWith('52.1.2.4')
      expect(wrapper.find('h1').text()).toBe('52.1.2.4')
      expect(find('device-connections').exists()).toBe(true)
    })

    it('ignores the answer for an address it has moved on from', async () => {
      const { fetchDevice, router, wrapper } = await open()
      let late: (answer: devicesApi.DeviceDetail) => void = () => {}
      fetchDevice.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      fetchDevice.mockResolvedValueOnce(deviceDetail({ device: device({ address: '9.9.9.9' }) }))

      await router.push('/devices/1.1.1.1')
      await router.push('/devices/9.9.9.9')
      await flushPromises()
      late(deviceDetail({ device: device({ address: '1.1.1.1' }) }))
      await flushPromises()

      expect(wrapper.find('h1').text()).toBe('9.9.9.9')
    })

    it('ignores the failure for an address it has moved on from', async () => {
      const { fetchDevice, router, wrapper } = await open()
      let fail: (reason: Error) => void = () => {}
      fetchDevice.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      fetchDevice.mockResolvedValueOnce(deviceDetail({ device: device({ address: '9.9.9.9' }) }))

      await router.push('/devices/1.1.1.1')
      await router.push('/devices/9.9.9.9')
      await flushPromises()
      fail(offline())
      await flushPromises()

      expect(wrapper.find('[data-test="device-error"]').exists()).toBe(false)
      expect(wrapper.find('h1').text()).toBe('9.9.9.9')
    })
  })
})
