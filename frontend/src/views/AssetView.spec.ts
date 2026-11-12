import * as assetsApi from '@/api/assets'
import { ApiError } from '@/api/client'
import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import AssetEvents from '@/components/AssetEvents.vue'
import AssetPeers from '@/components/AssetPeers.vue'
import { formatBytes } from '@/format'
import { asset, identity, kindGroups, profile } from '@/test/assets'
import {
  address,
  detail,
  event,
  incident,
  peer,
  reading,
  traffic,
  verdict,
} from '@/test/assetDetail'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AssetView from '@/views/AssetView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

interface Options {
  route?: string
  answer?: assetsApi.AssetDetail | Error
}

async function open({ route = '/assets/device-1', answer = detail() }: Options = {}) {
  vi.spyOn(assetsApi, 'fetchKinds').mockResolvedValue(kindGroups())
  const fetchAsset = vi.spyOn(assetsApi, 'fetchAsset')
  if (answer instanceof Error) fetchAsset.mockRejectedValue(answer)
  else fetchAsset.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(AssetView, { signedIn: 'admin', withApp: true, route })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const findAll = (selector: string) => mounted.wrapper.findAll(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  return { ...mounted, fetchAsset, find, findAll, text }
}

/** Twenty-four hours of readings, an hour apart, and a week of days, for the chart. */
const hours = Array.from({ length: 24 }, (_, index) =>
  reading({
    at: new Date(Date.UTC(2026, 10, 1, index)).toISOString(),
    sent: index * 10,
    received: null,
  }),
)
const days = Array.from({ length: 7 }, (_, index) =>
  reading({ at: new Date(Date.UTC(2026, 10, index + 1)).toISOString(), sent: 100 }),
)

describe('AssetView', () => {
  it('says what Fingerbank thinks it is, when it was asked', async () => {
    const { find } = await open({ answer: detail({ asset: asset({ identity: identity() }) }) })

    expect(find('asset-identity-section').exists()).toBe(true)
    expect(find('identity-name').text()).toBe('Apple iPhone 16')
  })

  it('has no section about it before Fingerbank has been asked', async () => {
    const { find } = await open()

    expect(find('asset-identity-section').exists()).toBe(false)
  })

  it('asks for the page of the asset the address names', async () => {
    const { fetchAsset } = await open()

    expect(fetchAsset).toHaveBeenCalledWith('device-1')
  })

  it('says what the asset is under its name, and how it has been listed', async () => {
    const { wrapper, text } = await open()

    expect(wrapper.text()).toContain('Laptop')
    expect(wrapper.text()).toContain('Device · Example Devices Inc. · 00:11:22:0a:0b:0c')
    expect(text('asset-tile-listed')).toContain('Online')
  })

  it('says what the owner said it is, and what it is for', async () => {
    const { find, text } = await open({
      answer: detail({ asset: asset({ profile: profile() }) }),
    })

    expect(text('asset-kind')).toBe('Camera or doorbell')
    expect(text('asset-purpose-line')).toBe('Watches the front door')
    expect(find('asset-classify').exists()).toBe(true)
  })

  it('offers to classify it when nothing was said, without a line about what it is for', async () => {
    const { find } = await open()

    expect(find('asset-kind').exists()).toBe(false)
    expect(find('asset-purpose-line').exists()).toBe(false)
    expect(find('asset-classify').exists()).toBe(true)
  })

  it('shows the kind without a purpose line when none was said', async () => {
    const { find } = await open({
      answer: detail({ asset: asset({ profile: profile({ purpose: null }) }) }),
    })

    expect(find('asset-kind').exists()).toBe(true)
    expect(find('asset-purpose-line').exists()).toBe(false)
  })

  it('reads the page again when what the owner says is saved', async () => {
    vi.spyOn(assetsApi, 'classifyAsset').mockResolvedValue(profile())
    const { fetchAsset, find, wrapper } = await open()
    const calls = fetchAsset.mock.calls.length

    await wrapper.find('[data-test="asset-kind-choice"]').trigger('click')
    await find('asset-classify-save').trigger('click')
    await flushPromises()

    expect(fetchAsset.mock.calls).toHaveLength(calls + 1)
  })

  it('says what the traffic was, once ntopng has measured it', async () => {
    const { text } = await open({
      answer: detail({ traffic: traffic({ measured: true, sent_day: 2048, received_day: 4096 }) }),
    })

    expect(text('asset-tile-sent')).toContain(formatBytes(2048))
    expect(text('asset-tile-received')).toContain(formatBytes(4096))
  })

  it('shows a dash for the traffic that nothing has measured yet', async () => {
    const { text } = await open()

    expect(text('asset-tile-sent')).toContain('–')
    expect(text('asset-tile-sent')).toContain('Nothing measured yet')
  })

  it('charts the last day by the hour, and the last week by the day, as it is asked', async () => {
    const { wrapper } = await open({
      answer: detail({ traffic: traffic({ measured: true, hours, days }) }),
    })
    const chart = wrapper.findComponent(TimeSeriesChart)
    const buttons = wrapper.findAll('[data-test="asset-window"] .v-btn')

    expect(chart.props('times')).toHaveLength(24)
    expect(chart.props('series').at(0)).toMatchObject({ id: 'sent' })
    expect(chart.props('series').at(0)?.values[3]).toBe(30)

    await buttons.at(1)?.trigger('click')
    await flushPromises()
    expect(chart.props('times')).toHaveLength(7)

    await buttons.at(0)?.trigger('click')
    await flushPromises()
    expect(chart.props('times')).toHaveLength(24)
  })

  it('says which interfaces it is on', async () => {
    const { findAll } = await open({
      answer: detail({
        networks: [
          { id: 4, name: 'Home' },
          { id: 5, name: 'IoT' },
        ],
      }),
    })

    expect(findAll('asset-network').map((item) => item.text())).toEqual(['Home', 'IoT'])
  })

  it('lists each address as now or before, with when it was seen', async () => {
    const { findAll } = await open({
      answer: detail({
        addresses: [address(), address({ address: '192.168.1.19', current: false })],
      }),
    })

    expect(findAll('asset-address-now').map((item) => item.text())).toEqual(['Now', 'Before'])
    expect(findAll('asset-address').at(1)?.text()).toContain('192.168.1.19')
  })

  it('says when no address is listed for it', async () => {
    const { find } = await open({ answer: detail({ addresses: [] }) })

    expect(find('asset-no-addresses').exists()).toBe(true)
  })

  it('lists the events its addresses were in, and how many there were in the week', async () => {
    const { wrapper, text } = await open({
      answer: detail({ events: [event()], events_day: 1, events_week: 4 }),
    })

    expect(wrapper.findComponent(AssetEvents).props('events')).toHaveLength(1)
    expect(text('asset-events-note')).toContain('4 in the last week')
  })

  it('says nothing happened in the week when nothing did', async () => {
    const { find, text } = await open()

    expect(text('asset-events-note')).toBe('Nothing in the last week.')
    expect(find('asset-event').exists()).toBe(false)
  })

  it('shows what it talked to, and what talked to it', async () => {
    const { wrapper } = await open({
      answer: detail({ talks_to: [peer()], contacted_by: [] }),
    })
    const peers = wrapper.findComponent(AssetPeers)

    expect(peers.props('talksTo')).toHaveLength(1)
    expect(peers.props('contactedBy')).toEqual([])
  })

  it('lists its incidents, each of which goes to its own page', async () => {
    const { find } = await open({ answer: detail({ incidents: [incident()] }) })

    expect(find('asset-incident').attributes('href')).toBe('/incidents/7')
    expect(find('asset-incident').text()).toContain('Repeated sign-in failures')
  })

  it('says when none of its addresses is in an incident', async () => {
    const { find } = await open()

    expect(find('asset-no-incidents').exists()).toBe(true)
  })

  it('lists the verdicts given about it, with what each one is about', async () => {
    const { findAll } = await open({
      answer: detail({
        verdicts: [
          verdict(),
          verdict({
            id: 4,
            verdict: 'threat',
            destination: '52.1.2.0/24',
            signature: 'Port scan',
          }),
        ],
      }),
    })
    const rows = findAll('asset-verdict')

    expect(rows).toHaveLength(2)
    expect(rows.at(0)?.text()).toContain('Not suspicious')
    expect(rows.at(0)?.text()).toContain('everything it does')
    expect(rows.at(1)?.text()).toContain('Real threat')
    expect(rows.at(1)?.text()).toContain('its traffic to 52.1.2.0/24 and the alert "Port scan"')
  })

  it('says when no verdict has been given about it', async () => {
    const { find } = await open()

    expect(find('asset-no-verdicts').exists()).toBe(true)
  })

  it('says the asset is not there when it is not on the list', async () => {
    const { find } = await open({
      answer: new ApiError(404, 'There is no asset with that key.', 'not_found'),
    })

    expect(find('asset-missing').exists()).toBe(true)
    expect(find('asset-error').exists()).toBe(false)
  })

  it('shows the error when the page cannot be read, and asks again when it is retried', async () => {
    const { find, fetchAsset } = await open({ answer: offline() })

    expect(find('asset-error').exists()).toBe(true)

    fetchAsset.mockResolvedValue(detail())
    await find('asset-retry').trigger('click')
    await flushPromises()

    expect(fetchAsset).toHaveBeenCalledTimes(2)
    expect(find('asset-error').exists()).toBe(false)
    expect(find('asset-tile-listed').exists()).toBe(true)
  })

  it('shows the message of a failure that is not from the server', async () => {
    const { find } = await open({ answer: new Error('Something broke.') })

    expect(find('asset-error').exists()).toBe(true)
  })

  it('shows a skeleton while the page is on its way', async () => {
    vi.spyOn(assetsApi, 'fetchAsset').mockReturnValue(new Promise(() => {}))
    const mounted = await mountWithPlugins(AssetView, {
      signedIn: 'admin',
      withApp: true,
      route: '/assets/device-1',
    })
    await flushPromises()

    expect(mounted.wrapper.find('[data-test="asset-loading"]').exists()).toBe(true)
  })

  it('drops the answer for an asset the page has moved on from', async () => {
    const { router, fetchAsset, wrapper } = await open()
    let late: (answer: assetsApi.AssetDetail) => void = () => {}
    fetchAsset.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
    fetchAsset.mockResolvedValueOnce(detail({ asset: asset({ key: 'device-3', name: 'Phone' }) }))

    await router.push('/assets/device-2')
    await router.push('/assets/device-3')
    await flushPromises()
    late(detail({ asset: asset({ key: 'device-2', name: 'Tablet' }) }))
    await flushPromises()

    expect(fetchAsset).toHaveBeenNthCalledWith(2, 'device-2')
    expect(fetchAsset).toHaveBeenNthCalledWith(3, 'device-3')
    expect(wrapper.text()).toContain('Phone')
    expect(wrapper.text()).not.toContain('Tablet')
  })

  it('drops a failure for an asset the page has moved on from', async () => {
    const { router, fetchAsset, find } = await open()
    let late: (error: Error) => void = () => {}
    fetchAsset.mockReturnValueOnce(new Promise((_, reject) => (late = reject)))
    fetchAsset.mockResolvedValueOnce(detail({ asset: asset({ key: 'device-3', name: 'Phone' }) }))

    await router.push('/assets/device-2')
    await router.push('/assets/device-3')
    await flushPromises()
    late(offline())
    await flushPromises()

    expect(find('asset-error').exists()).toBe(false)
    expect(find('asset-tile-listed').exists()).toBe(true)
  })

  it('asks again every half minute, and keeps what is on screen when that fails', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const { fetchAsset, find } = await open()
      fetchAsset.mockRejectedValue(offline())

      vi.advanceTimersByTime(30_000)
      await flushPromises()

      expect(fetchAsset).toHaveBeenCalledTimes(2)
      expect(find('asset-error').exists()).toBe(false)
      expect(find('asset-tile-listed').exists()).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows the error of a refresh when there is no page yet to keep', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      vi.spyOn(assetsApi, 'fetchAsset')
        .mockReturnValueOnce(new Promise(() => {}))
        .mockRejectedValueOnce(offline())
      const mounted = await mountWithPlugins(AssetView, {
        signedIn: 'admin',
        withApp: true,
        route: '/assets/device-1',
      })

      vi.advanceTimersByTime(30_000)
      await flushPromises()

      expect(mounted.wrapper.find('[data-test="asset-error"]').exists()).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })
})
