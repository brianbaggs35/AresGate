import { VSelect } from 'vuetify/components'

import * as alertsApi from '@/api/alerts'
import { ApiError } from '@/api/client'
import DeliveryLog from '@/components/DeliveryLog.vue'
import { deliveries, delivery } from '@/test/alerts'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const ONE = [{ id: 1, name: 'Security channel' }]
const TWO = [...ONE, { id: 2, name: 'Phone' }]

async function open(
  first: alertsApi.Deliveries | Error = deliveries(),
  destinations: typeof ONE = ONE,
) {
  const fetch = vi.spyOn(alertsApi, 'fetchDeliveries')
  if (first instanceof Error) fetch.mockRejectedValue(first)
  else fetch.mockResolvedValue(first)
  const mounted = await mountWithPlugins(DeliveryLog, {
    signedIn: 'admin',
    props: { destinations },
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const rows = () => mounted.wrapper.findAll('[data-test="delivery"]')
  const choose = async (filter: string, value: string) => {
    mounted.wrapper
      .findAllComponents(VSelect)
      .find((select) => select.attributes('data-test') === `delivery-filter-${filter}`)
      ?.vm.$emit('update:modelValue', value)
    await flushPromises()
  }
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  return { ...mounted, fetch, find, rows, choose, click }
}

describe('DeliveryLog', () => {
  it('asks for the newest messages', async () => {
    const { fetch } = await open()
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledWith({})
  })

  it('shows what each message was, where it went, why and when', async () => {
    const { rows, find } = await open(
      deliveries([
        delivery({ id: 2, reason: 'worse', title: 'SSH guessing', incident_id: 3 }),
        delivery({ id: 1, attempts: 3 }),
      ]),
    )
    expect(rows()).toHaveLength(2)
    const [newest, oldest] = rows()
    expect(newest?.find('[data-test="delivery-state"]').text()).toBe('Sent')
    expect(newest?.find('[data-test="delivery-title"]').text()).toBe('SSH guessing')
    expect(newest?.find('a').attributes('href')).toBe('/incidents/3')
    expect(newest?.find('[data-test="delivery-detail"]').text()).toBe(
      'Security channel · Got worse · sent 5 minutes ago',
    )
    expect(oldest?.find('[data-test="delivery-detail"]').text()).toContain('· 3 tries')
    expect(find('delivery-totals').text()).toBe('2 sent, 0 waiting, 0 not sent')
  })

  it('says why a message was held, waited or not sent', async () => {
    const { rows } = await open(
      deliveries(
        [
          delivery({
            id: 3,
            state: 'held',
            sent_at: null,
            due_at: new Date(Date.now() + 3_600_000).toISOString(),
            note: null,
          }),
          delivery({ id: 2, state: 'failed', sent_at: null, note: 'Discord had a fault.' }),
          delivery({ id: 1, state: 'dropped', sent_at: null, note: 'Not sent. You resolved it.' }),
        ],
        { counts: { held: 1, failed: 1, dropped: 1 } },
      ),
    )
    const [held, failed, dropped] = rows()
    expect(held?.find('[data-test="delivery-state"]').text()).toBe('Held for quiet hours')
    expect(held?.find('[data-test="delivery-detail"]').text()).toMatch(/due in (1 hour|60 minutes)/)
    expect(held?.find('[data-test="delivery-note"]').exists()).toBe(false)
    expect(failed?.find('[data-test="delivery-note"]').text()).toBe('Discord had a fault.')
    expect(failed?.find('[data-test="delivery-detail"]').text()).toContain('made 6 minutes ago')
    expect(dropped?.find('[data-test="delivery-state"]').text()).toBe('Left out')
  })

  it('names a summary by how many incidents it told of, and links to none', async () => {
    const { rows } = await open(
      deliveries([
        delivery({
          id: 2,
          kind: 'summary',
          reason: 'limit',
          incident_id: null,
          covers: 4,
          severity: 'info',
        }),
        delivery({ id: 1, kind: 'summary', reason: 'quiet', incident_id: null, covers: 1 }),
      ]),
    )
    const [limited, quiet] = rows()
    expect(limited?.find('[data-test="delivery-title"]').text()).toBe(
      '4 incidents held back by the limit',
    )
    expect(limited?.find('a').exists()).toBe(false)
    expect(limited?.find('[data-test="severity"]').exists()).toBe(false)
    expect(quiet?.find('[data-test="delivery-title"]').text()).toBe(
      '1 incident came in during quiet hours',
    )
  })

  it('shows what a system said as plain text, never as markup', async () => {
    const hostile = '<img src=x onerror=alert(1)>'
    const { wrapper, rows } = await open(deliveries([delivery({ state: 'failed', note: hostile })]))
    expect(rows()[0]?.find('[data-test="delivery-note"]').text()).toBe(hostile)
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('says when nothing has been sent yet', async () => {
    const { find } = await open(deliveries([], { counts: {} }))
    expect(find('delivery-empty').text()).toContain('Nothing has been sent yet')
    expect(find('delivery-totals').text()).toBe('Nothing yet.')
    expect(find('delivery-clear').exists()).toBe(false)
  })

  it('shows a placeholder while it asks', async () => {
    vi.spyOn(alertsApi, 'fetchDeliveries').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(DeliveryLog, {
      signedIn: 'admin',
      props: { destinations: ONE },
    })
    expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
    expect(wrapper.find('[data-test="delivery-totals"]').exists()).toBe(false)
  })

  describe('the filters', () => {
    it('has a filter for the destination only when there are several', async () => {
      const one = await open()
      expect(one.find('delivery-filter-destination').exists()).toBe(false)
      const two = await open(deliveries(), TWO)
      expect(two.find('delivery-filter-destination').exists()).toBe(true)
    })

    it('narrows to a destination and to a state, and back', async () => {
      const { fetch, choose } = await open(deliveries(), TWO)
      await choose('destination', '2')
      expect(fetch).toHaveBeenLastCalledWith({ destination_id: 2 })
      await choose('state', 'failed')
      expect(fetch).toHaveBeenLastCalledWith({ destination_id: 2, state: 'failed' })
      await choose('destination', 'all')
      await choose('state', 'all')
      expect(fetch).toHaveBeenLastCalledWith({})
    })

    it('says nothing matches, and clears the filters', async () => {
      const { fetch, choose, find, click } = await open()
      fetch.mockResolvedValue(deliveries([], { counts: {} }))
      await choose('state', 'failed')
      expect(find('delivery-empty').text()).toContain('No messages match these filters.')
      fetch.mockResolvedValue(deliveries())
      await click('delivery-clear')
      expect(fetch).toHaveBeenLastCalledWith({})
      expect(find('delivery-list').exists()).toBe(true)
    })
  })

  describe('older messages', () => {
    it('offers them only when there are more, and adds them to the end', async () => {
      const { fetch, rows, find, click } = await open(
        deliveries([delivery({ id: 2 })], { next_before: 2 }),
      )
      fetch.mockResolvedValue(deliveries([delivery({ id: 1 })]))
      await click('delivery-older')
      expect(fetch).toHaveBeenLastCalledWith({ before: 2 })
      expect(rows()).toHaveLength(2)
      expect(find('delivery-older').exists()).toBe(false)
    })

    it('is not offered on the last page', async () => {
      const { find } = await open()
      expect(find('delivery-older').exists()).toBe(false)
    })
  })

  describe('when it cannot load', () => {
    it('says why, and tries again', async () => {
      const { fetch, find, rows, click } = await open(
        new ApiError(0, "Can't reach AresGate.", 'offline'),
      )
      expect(find('delivery-error').text()).toContain("Can't reach AresGate.")
      expect(find('delivery-empty').exists()).toBe(false)
      fetch.mockResolvedValue(deliveries())
      await click('delivery-retry')
      expect(rows()).toHaveLength(1)
      expect(find('delivery-error').exists()).toBe(false)
    })

    it('keeps the list when only older messages could not be read', async () => {
      const { fetch, find, rows, click } = await open(
        deliveries([delivery({ id: 2 })], { next_before: 2 }),
      )
      fetch.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))
      await click('delivery-older')
      expect(find('delivery-error').exists()).toBe(true)
      expect(rows()).toHaveLength(1)
    })

    it('drops the list when the newest messages could not be read again', async () => {
      const { fetch, find, rows, click } = await open()
      fetch.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))
      await click('delivery-refresh')
      expect(find('delivery-error').exists()).toBe(true)
      expect(rows()).toHaveLength(1)
      expect(find('delivery-totals').exists()).toBe(false)
    })
  })

  it('reloads on Refresh', async () => {
    const { fetch, click } = await open()
    await click('delivery-refresh')
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('uses only the newest answer when two are asked for', async () => {
    const { fetch, choose, rows } = await open(deliveries([delivery({ id: 9 })]))
    let slow: (value: alertsApi.Deliveries) => void = () => {}
    fetch.mockReturnValueOnce(
      new Promise((resolve) => {
        slow = resolve
      }),
    )
    await choose('state', 'failed')
    fetch.mockResolvedValue(deliveries([delivery({ id: 5 }), delivery({ id: 4 })]))
    await choose('state', 'sent')
    slow(deliveries([delivery({ id: 1 })]))
    await flushPromises()
    expect(rows()).toHaveLength(2)
  })

  it('ignores the failure of a request that a newer one has replaced', async () => {
    const { fetch, choose, rows, find } = await open()
    let fail: (reason: Error) => void = () => {}
    fetch.mockReturnValueOnce(
      new Promise((_, reject) => {
        fail = reject
      }),
    )
    await choose('state', 'failed')
    fetch.mockResolvedValue(deliveries([delivery({ id: 5 }), delivery({ id: 4 })]))
    await choose('state', 'sent')
    fail(new ApiError(0, "Can't reach AresGate.", 'offline'))
    await flushPromises()
    expect(find('delivery-error').exists()).toBe(false)
    expect(rows()).toHaveLength(2)
  })
})
