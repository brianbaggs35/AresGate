import { flushPromises } from '@vue/test-utils'

import * as trends from '@/api/trends'
import DeviceTraffic from '@/components/DeviceTraffic.vue'
import { mountWithPlugins } from '@/test/mount'
import { addressTrends } from '@/test/trends'

describe('DeviceTraffic', () => {
  it('charts the connections in and out of a device over the week', async () => {
    const fetch = vi.spyOn(trends, 'fetchAddressTrends').mockResolvedValue(addressTrends())

    const { wrapper } = await mountWithPlugins(DeviceTraffic, {
      props: { address: '192.168.1.20' },
    })
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith(['192.168.1.20'], 'hour', 168)
    expect(wrapper.find('[data-test="device-traffic"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="chart-legend-item"]').map((item) => item.text())).toEqual([
      'Connections in',
      'Connections out',
    ])
  })

  it('says there were none when the answer has nothing for the device', async () => {
    vi.spyOn(trends, 'fetchAddressTrends').mockResolvedValue(addressTrends({}))

    const { wrapper } = await mountWithPlugins(DeviceTraffic, {
      props: { address: '192.168.1.20' },
    })
    await flushPromises()

    expect(wrapper.find('[data-test="empty-title"]').text()).toBe('No connections')
  })

  it('is not there when it cannot be had', async () => {
    vi.spyOn(trends, 'fetchAddressTrends').mockRejectedValue(new Error('down'))

    const { wrapper } = await mountWithPlugins(DeviceTraffic, {
      props: { address: '192.168.1.20' },
    })
    await flushPromises()

    expect(wrapper.find('[data-test="device-traffic"]').exists()).toBe(false)
  })
})
