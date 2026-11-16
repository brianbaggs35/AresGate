import { flushPromises } from '@vue/test-utils'

import * as trends from '@/api/trends'
import DeliveryTrend from '@/components/DeliveryTrend.vue'
import { mountWithPlugins } from '@/test/mount'
import { deliveryTrend } from '@/test/trends'

describe('DeliveryTrend', () => {
  it('charts the messages of each hour by severity once they are known', async () => {
    const fetch = vi.spyOn(trends, 'fetchDeliveryTrend').mockResolvedValue(deliveryTrend())

    const { wrapper } = await mountWithPlugins(DeliveryTrend, {
      props: { destination: 4, state: 'failed' },
    })
    await flushPromises()

    expect(fetch).toHaveBeenCalledWith({ destination_id: 4, state: 'failed' })
    expect(wrapper.find('[data-test="delivery-trend"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="chart-title"]').text()).toBe('Messages by severity')
    expect(wrapper.findAll('[data-test="chart-legend-item"]').map((item) => item.text())).toEqual([
      'Medium',
      'High',
    ])
  })

  it('says nothing was sent when no message was made', async () => {
    vi.spyOn(trends, 'fetchDeliveryTrend').mockResolvedValue(
      deliveryTrend({ severities: { info: [0], low: [0], medium: [0], high: [0], critical: [0] } }),
    )

    const { wrapper } = await mountWithPlugins(DeliveryTrend)
    await flushPromises()

    expect(wrapper.find('[data-test="empty-title"]').text()).toBe('No messages')
  })

  it('asks again when the log is filtered differently', async () => {
    const fetch = vi.spyOn(trends, 'fetchDeliveryTrend').mockResolvedValue(deliveryTrend())
    const { wrapper } = await mountWithPlugins(DeliveryTrend)
    await flushPromises()

    await wrapper.setProps({ state: 'sent' })
    await flushPromises()

    expect(fetch).toHaveBeenLastCalledWith({ destination_id: undefined, state: 'sent' })
  })

  it('is not there when it cannot be had', async () => {
    vi.spyOn(trends, 'fetchDeliveryTrend').mockRejectedValue(new Error('down'))

    const { wrapper } = await mountWithPlugins(DeliveryTrend)
    await flushPromises()

    expect(wrapper.find('[data-test="delivery-trend"]').exists()).toBe(false)
  })
})
