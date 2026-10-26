import ChartFrame from '@/charts/ChartFrame.vue'
import type { LegendItem } from '@/charts/types'
import { mountWithPlugins } from '@/test/mount'

const legend: LegendItem[] = [
  { id: 'a', label: 'Received', color: 'red', shape: 'line' },
  { id: 'b', label: 'Sent', color: 'blue', shape: 'line' },
]
const table = { columns: ['Time', 'Received', 'Sent'], rows: [['6 PM', '1', '2']] }
const slots = { default: '<svg data-test="plot" />' }

function mountFrame(props: Record<string, unknown> = {}) {
  return mountWithPlugins(ChartFrame, {
    props: { title: 'Throughput', legend, table, hidden: [], ...props },
    slots,
  })
}

describe('ChartFrame', () => {
  it('holds the chart under its title and what it shows, and names the group by the title', async () => {
    const { wrapper } = await mountFrame({ caption: 'Last 24 hours' })

    expect(wrapper.find('[data-test="chart-title"]').text()).toBe('Throughput')
    expect(wrapper.find('[data-test="chart-caption"]').text()).toBe('Last 24 hours')
    expect(wrapper.find('[data-test="plot"]').exists()).toBe(true)
    const group = wrapper.find('[data-test="chart"]')
    expect(group.attributes('aria-labelledby')).toBe(
      wrapper.find('[data-test="chart-title"]').attributes('id'),
    )
  })

  it('has no caption unless it is given one', async () => {
    const { wrapper } = await mountFrame()

    expect(wrapper.find('[data-test="chart-caption"]').exists()).toBe(false)
  })

  it('shows a legend for two series, and passes on what is turned off', async () => {
    const { wrapper } = await mountFrame()

    expect(wrapper.find('[data-test="chart-legend"]').exists()).toBe(true)
    await wrapper.findAll('[data-test="chart-legend-item"]')[0]?.trigger('click')
    expect(wrapper.emitted('update:hidden')).toEqual([[['a']]])
  })

  it('has no legend for one series, which the title already names', async () => {
    const { wrapper } = await mountFrame({ legend: [legend[0]] })

    expect(wrapper.find('[data-test="chart-legend"]').exists()).toBe(false)
  })

  it('swaps the chart for the same numbers as a table, and back', async () => {
    const { wrapper } = await mountFrame()
    const toggle = wrapper.find('[data-test="chart-view"]')
    expect(toggle.text()).toBe('Show as table')

    await toggle.trigger('click')

    expect(wrapper.find('[data-test="plot"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="chart-table"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="chart-legend"]').exists()).toBe(false)
    expect(toggle.text()).toBe('Show chart')

    await toggle.trigger('click')

    expect(wrapper.find('[data-test="plot"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="chart-table"]').exists()).toBe(false)
  })

  it('says there is nothing to show instead of drawing an empty chart', async () => {
    const { wrapper } = await mountFrame({ empty: true })

    expect(wrapper.find('[data-test="plot"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="chart-view"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="chart-legend"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="empty-title"]').text()).toBe('Nothing to show yet')
    expect(wrapper.find('[data-test="empty-text"]').exists()).toBe(false)
  })

  it('says why there is nothing, in the words it is given', async () => {
    const { wrapper } = await mountFrame({
      empty: true,
      emptyTitle: 'Nothing blocked',
      emptyDescription: 'No connections were blocked.',
    })

    expect(wrapper.find('[data-test="empty-title"]').text()).toBe('Nothing blocked')
    expect(wrapper.find('[data-test="empty-text"]').text()).toBe('No connections were blocked.')
  })

  it('keeps the chart, dimmed, while fresh data loads', async () => {
    const { wrapper } = await mountFrame({ loading: true })

    expect(wrapper.find('[data-test="plot"]').exists()).toBe(true)
    expect(wrapper.find('.chart-frame__plot').classes()).toContain('chart-frame__plot--loading')
    expect(wrapper.find('[data-test="chart"]').attributes('aria-busy')).toBe('true')
  })

  it('is not busy when nothing is loading', async () => {
    const { wrapper } = await mountFrame()

    expect(wrapper.find('.chart-frame__plot').classes()).not.toContain('chart-frame__plot--loading')
    expect(wrapper.find('[data-test="chart"]').attributes('aria-busy')).toBeUndefined()
  })
})
