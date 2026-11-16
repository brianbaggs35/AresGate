import { Siren } from '@lucide/vue'
import { VSelect } from 'vuetify/components'

import type { InterfaceTraffic } from '@/api/dashboard'
import type { ChartMark } from '@/charts/types'
import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import TrafficCard from '@/components/TrafficCard.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const times = [0, 900_000, 1_800_000, 2_700_000]
const igc0: InterfaceTraffic = {
  interface: 'igc0',
  received: [null, 8_000_000, 80_000_000, 40_000_000],
  sent: [null, 2_000_000, 20_000_000, 10_000_000],
}
const igc1: InterfaceTraffic = {
  interface: 'igc1',
  received: [null, 1_000, 2_000, 3_000],
  sent: [null, 100, 200, 300],
}

const mount = (traffic: InterfaceTraffic[], loading = false) =>
  mountWithPlugins(TrafficCard, { props: { times, traffic, loading } })

describe('TrafficCard', () => {
  it('charts what was received and sent through the first interface', async () => {
    const { wrapper } = await mount([igc0, igc1])
    expect(wrapper.find('[data-test="chart-title"]').text()).toBe('Network traffic')
    expect(wrapper.find('[data-test="chart-caption"]').text()).toContain('igc0')
    expect(wrapper.findAll('[data-test="line"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('Received')
    expect(wrapper.text()).toContain('Sent')
  })

  it('hands the incidents to the chart, to flag above the lines', async () => {
    const mark: ChartMark = {
      id: 'incident-1',
      time: 1_800_000,
      weight: 3070,
      label: 'High incident: Brute force',
      heading: 'Began 2:30 PM',
      rows: [{ label: 'High', value: 'Brute force' }],
      color: 'red',
      icon: Siren,
      to: { name: 'incident', params: { id: 1 } },
    }
    const { wrapper } = await mountWithPlugins(TrafficCard, {
      props: { times, traffic: [igc0], marks: [mark] },
    })
    expect(wrapper.findComponent(TimeSeriesChart).props('marks')).toEqual([mark])
  })

  it('flags nothing unless told', async () => {
    const { wrapper } = await mount([igc0])
    expect(wrapper.findComponent(TimeSeriesChart).props('marks')).toEqual([])
  })

  it('reads speeds in bits a second', async () => {
    const { wrapper } = await mount([igc0])
    expect(wrapper.text()).toMatch(/\d+ Mb\/s/)
  })

  it('has no menu when there is only one interface', async () => {
    const { wrapper } = await mount([igc0])
    expect(wrapper.find('[data-test="traffic-interface"]').exists()).toBe(false)
  })

  it('offers the interfaces, and charts the one chosen', async () => {
    const { wrapper } = await mount([igc0, igc1])
    const menu = wrapper.findComponent(VSelect)
    expect(menu.exists()).toBe(true)
    menu.vm.$emit('update:modelValue', 'igc1')
    await flushPromises()
    expect(wrapper.find('[data-test="chart-caption"]').text()).toContain('igc1')
  })

  it('falls back to the first when the one chosen is gone', async () => {
    const { wrapper } = await mount([igc0, igc1])
    wrapper.findComponent(VSelect).vm.$emit('update:modelValue', 'igc1')
    await flushPromises()
    await wrapper.setProps({ traffic: [igc0] })
    expect(wrapper.find('[data-test="chart-caption"]').text()).toContain('igc0')
  })

  it('says so when no traffic has been recorded', async () => {
    const { wrapper } = await mount([])
    expect(wrapper.find('[data-test="chart-empty"]').text()).toContain('No traffic recorded yet')
    expect(wrapper.find('[data-test="chart-caption"]').exists()).toBe(false)
  })

  it('dims the chart while it loads', async () => {
    const { wrapper } = await mount([igc0], true)
    expect(wrapper.find('.chart-frame__plot--loading').exists()).toBe(true)
  })

  describe('zooming and opening', () => {
    it('draws only the span the page is zoomed to, with the incidents that fall in it', async () => {
      const inside: ChartMark = {
        id: 'incident-1',
        time: 1_000_000,
        weight: 1,
        label: 'In',
        heading: 'In',
        rows: [{ label: 'High', value: 'In' }],
        color: 'red',
        icon: Siren,
        to: { name: 'incident', params: { id: 1 } },
      }
      const outside: ChartMark = { ...inside, id: 'incident-2', time: 2_700_000, label: 'Out' }
      const { wrapper } = await mountWithPlugins(TrafficCard, {
        props: { times, traffic: [igc0], marks: [inside, outside], span: [900_000, 1_800_000] },
      })

      const chart = wrapper.findComponent(TimeSeriesChart)
      expect(chart.props('times')).toEqual([900_000, 1_800_000])
      expect(chart.props('series')[0]?.values).toEqual([8_000_000, 80_000_000])
      expect(chart.props('marks')).toEqual([inside])
      expect(chart.props('zoomed')).toBe(true)
      expect(chart.props('zoomable')).toBe(true)
    })

    it('draws all of it with no span, and is not zoomed', async () => {
      const { wrapper } = await mount([igc0])

      const chart = wrapper.findComponent(TimeSeriesChart)
      expect(chart.props('times')).toEqual(times)
      expect(chart.props('zoomed')).toBe(false)
    })

    it('passes on a zoom and a reset', async () => {
      const { wrapper } = await mount([igc0])
      const chart = wrapper.findComponent(TimeSeriesChart)

      chart.vm.$emit('zoom', 900_000, 1_800_000)
      chart.vm.$emit('reset')

      expect(wrapper.emitted('zoom')).toEqual([[900_000, 1_800_000]])
      expect(wrapper.emitted('reset')).toEqual([[]])
    })

    it('opens the firewall logs of the stretch of time a reading stands for', async () => {
      const { wrapper } = await mount([igc0])
      const to = wrapper.findComponent(TimeSeriesChart).props('to') as (time: number) => unknown

      expect(to(900_000)).toEqual({
        name: 'logs',
        query: { q: 'kind:firewall since:1970-01-01T00:15:00Z before:1970-01-01T00:30:00Z' },
      })
    })
  })
})
