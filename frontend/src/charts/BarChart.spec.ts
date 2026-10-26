import { Siren } from '@lucide/vue'

import BarChart from '@/charts/BarChart.vue'
import { mountWithPlugins } from '@/test/mount'

const hosts = ['192.168.1.20', 'living-room-tv.lan', 'printer']
const blocked = [{ id: 'blocked', label: 'Blocked', values: [12_408, 4210, 0] }]

function mountBars(props: Record<string, unknown> = {}) {
  return mountWithPlugins(BarChart, {
    props: { title: 'Busiest hosts', categories: hosts, series: blocked, ...props },
  })
}

/** What the chart's own text says: the bar values and the readout a screen reader hears. */
const values = (wrapper: { findAll: (selector: string) => { text: () => string }[] }) =>
  wrapper.findAll('[data-test="bar-value"]').map((value) => value.text())

describe('BarChart', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('horizontal', () => {
    it('draws a bar for each category that has something, with its value at the tip', async () => {
      const { wrapper } = await mountBars()

      expect(wrapper.findAll('[data-test="bar"]')).toHaveLength(2)
      expect(values(wrapper)).toEqual(['12,408', '4,210'])
      expect(wrapper.findAll('[data-test="bar-category"]').map((name) => name.text())).toEqual(
        hosts,
      )
      expect(wrapper.find('[data-test="chart-legend"]').exists()).toBe(false)
    })

    it('colors a series with the next hue unless it has a color of its own', async () => {
      const { wrapper } = await mountBars()
      expect(wrapper.find('[data-test="bar"]').attributes('fill')).toBe('var(--chart-1)')

      await wrapper.setProps({ series: [{ ...blocked[0], color: 'var(--chart-severity-high)' }] })
      expect(wrapper.find('[data-test="bar"]').attributes('fill')).toBe(
        'var(--chart-severity-high)',
      )
    })

    it('writes values the way it is told to', async () => {
      const { wrapper } = await mountBars({ format: (value: number) => `${value.toString()} B` })

      expect(values(wrapper)).toEqual(['12408 B', '4210 B'])
    })

    it('cuts a name short that would not fit beside its bar', async () => {
      const longName = 'a-very-long-hostname-for-a-device.home.arpa'
      const width = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get')
      width.mockReturnValue(900)
      const wide = await mountBars({ categories: [longName, 'b', 'c'] })
      width.mockReturnValue(300)
      const narrow = await mountBars({ categories: [longName, 'b', 'c'] })

      expect(wide.wrapper.find('[data-test="bar-category"]').text()).toBe(longName)
      const name = narrow.wrapper.find('[data-test="bar-category"]').text()
      expect(name.endsWith('…')).toBe(true)
      expect(name.length).toBeLessThan(longName.length)
    })

    it('has a legend for several series, side by side with no value on each bar', async () => {
      const { wrapper } = await mountBars({
        series: [
          { id: 'in', label: 'Received', values: [10, 20, 30] },
          { id: 'out', label: 'Sent', values: [5, 5, 5] },
        ],
      })

      expect(wrapper.findAll('[data-test="chart-legend-item"]')).toHaveLength(2)
      expect(wrapper.findAll('[data-test="bar"]')).toHaveLength(6)
      expect(values(wrapper)).toEqual([])
    })

    it('stacks series, with the total at the end of each stack', async () => {
      const { wrapper } = await mountBars({
        stacked: true,
        series: [
          { id: 'low', label: 'Low', values: [5, 2, 0] },
          { id: 'high', label: 'High', values: [3, 0, 0] },
        ],
      })

      expect(wrapper.findAll('[data-test="bar"]')).toHaveLength(3)
      expect(values(wrapper)).toEqual(['8', '2'])
    })
  })

  describe('vertical', () => {
    const hours = ['00:00', '01:00', '02:00']
    const vertical = {
      orientation: 'vertical',
      categories: hours,
      series: [{ id: 'alerts', label: 'Alerts', values: [12, 40, 0] }],
    }

    it('draws columns over a value axis with clean ticks and the value on each cap', async () => {
      const { wrapper } = await mountBars(vertical)

      expect(wrapper.findAll('[data-test="bar"]')).toHaveLength(2)
      expect(wrapper.findAll('.chart-grid')).toHaveLength(5)
      expect(wrapper.findAll('.chart-text').map((text) => text.text())).toEqual(
        expect.arrayContaining(['0', '10', '20', '30', '40']),
      )
      expect(values(wrapper)).toEqual(['12', '40'])
      expect(wrapper.findAll('[data-test="bar-category"]').map((name) => name.text())).toEqual(
        hours,
      )
    })

    it('writes the axis in short numbers unless it is told how to write values', async () => {
      const { wrapper } = await mountBars({
        ...vertical,
        series: [{ id: 'alerts', label: 'Alerts', values: [12_000, 40_000, 0] }],
      })

      expect(wrapper.findAll('.chart-text').map((text) => text.text())).toEqual(
        expect.arrayContaining(['0', '10K', '20K', '30K', '40K']),
      )
    })

    it('names only some of a crowded axis, and leaves off values that would crowd the caps', async () => {
      vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(320)
      const names = Array.from(
        { length: 24 },
        (_, hour) => `${hour.toString().padStart(2, '0')}:00`,
      )
      const { wrapper } = await mountBars({
        orientation: 'vertical',
        categories: names,
        series: [{ id: 'alerts', label: 'Alerts', values: names.map((_, hour) => hour + 1) }],
      })

      const named = wrapper
        .findAll('[data-test="bar-category"]')
        .map((name) => name.text())
        .filter(Boolean)
      expect(named.length).toBeGreaterThan(2)
      expect(named.length).toBeLessThan(24)
      expect(named[0]).toBe('00:00')
      expect(wrapper.find('[data-test="bar-value"]').attributes('display')).toBe('none')
    })

    it('stacks columns, and says the total with the parts', async () => {
      const { wrapper } = await mountBars({
        ...vertical,
        stacked: true,
        series: [
          { id: 'low', label: 'Low', values: [5, 10, 0] },
          { id: 'high', label: 'High', values: [7, 30, 0] },
        ],
      })

      expect(values(wrapper)).toEqual(['12', '40'])
      await wrapper.find('[data-test="bar-slot"]').trigger('pointerenter')
      expect(wrapper.findAll('[data-test="chart-tooltip-row"]').map((row) => row.text())).toEqual([
        '5Low',
        '7High',
        '12Total',
      ])
    })
  })

  describe('reading it', () => {
    it('says what a category holds under the pointer, and puts it away when the pointer leaves', async () => {
      const { wrapper } = await mountBars()
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)

      await wrapper.findAll('[data-test="bar-slot"]')[1]?.trigger('pointerenter')

      const tip = wrapper.find('[data-test="chart-tooltip"]')
      expect(tip.text()).toContain('living-room-tv.lan')
      expect(tip.findAll('[data-test="chart-tooltip-row"]').map((row) => row.text())).toEqual([
        '4,210Blocked',
      ])
      expect(wrapper.find('output').text()).toBe('living-room-tv.lan: 4,210 Blocked')
      // The other bars step back.
      expect(wrapper.findAll('.bar-chart__mark--dim')).toHaveLength(1)

      await wrapper.find('.chart-svg').trigger('pointerleave', { pointerType: 'mouse' })
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
      expect(wrapper.find('output').text()).toBe('')
    })

    it('opens the tooltip on the other side near the right edge of a horizontal chart', async () => {
      const { wrapper } = await mountBars()

      await wrapper.findAll('[data-test="bar-slot"]')[0]?.trigger('pointerenter')
      expect(wrapper.find('[data-test="chart-tooltip"]').classes()).toContain('chart-tooltip--flip')

      await wrapper.findAll('[data-test="bar-slot"]')[1]?.trigger('pointerenter')
      expect(wrapper.find('[data-test="chart-tooltip"]').classes()).not.toContain(
        'chart-tooltip--flip',
      )
    })

    it('points at a category with nothing in it without a bar', async () => {
      const { wrapper } = await mountBars()

      await wrapper.findAll('[data-test="bar-slot"]')[2]?.trigger('pointerenter')

      expect(wrapper.find('[data-test="chart-tooltip"]').text()).toContain('0Blocked')
    })

    it('keeps what a finger touched until it touches something else', async () => {
      const { wrapper } = await mountBars()

      await wrapper.findAll('[data-test="bar-slot"]')[0]?.trigger('pointerdown')
      await wrapper.find('.chart-svg').trigger('pointerleave', { pointerType: 'touch' })
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(true)

      await wrapper.find('.chart-svg').trigger('blur')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
    })

    it('reads each category in turn with the arrow keys, and puts them away with Escape', async () => {
      const { wrapper } = await mountBars()
      const chart = wrapper.find('.chart-svg')

      await chart.trigger('keydown', { key: 'ArrowDown' })
      expect(wrapper.find('output').text()).toContain('192.168.1.20')
      await chart.trigger('keydown', { key: 'End' })
      expect(wrapper.find('output').text()).toContain('printer')
      await chart.trigger('keydown', { key: 'ArrowUp' })
      expect(wrapper.find('output').text()).toContain('living-room-tv.lan')
      await chart.trigger('keydown', { key: 'Escape' })
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
    })

    it('leaves the other keys to the page', async () => {
      const { wrapper } = await mountBars()
      const event = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true })

      wrapper.find('.chart-svg').element.dispatchEvent(event)

      expect(event.defaultPrevented).toBe(false)
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
    })

    it('can be reached with the keyboard, and says what it is', async () => {
      const { wrapper } = await mountBars()

      const chart = wrapper.find('.chart-svg')
      expect(chart.attributes('tabindex')).toBe('0')
      expect(chart.attributes('role')).toBe('img')
      expect(chart.attributes('aria-label')).toContain('Busiest hosts')
    })
  })

  describe('as a table, with series turned off, and in its other states', () => {
    it('lists every value, and a total when it is stacked', async () => {
      const { wrapper } = await mountBars({
        categoryLabel: 'Host',
        stacked: true,
        series: [
          { id: 'low', label: 'Low', values: [5, 2, 0] },
          { id: 'high', label: 'High', values: [3, 0, 0] },
        ],
      })

      await wrapper.find('[data-test="chart-view"]').trigger('click')

      expect(wrapper.findAll('thead th').map((cell) => cell.text())).toEqual([
        'Host',
        'Low',
        'High',
        'Total',
      ])
      expect(wrapper.findAll('[data-test="chart-table-row"]')[0]?.text()).toBe('192.168.1.20538')
    })

    it('leaves out the total of one series or of series side by side', async () => {
      const { wrapper } = await mountBars()

      await wrapper.find('[data-test="chart-view"]').trigger('click')

      expect(wrapper.findAll('thead th').map((cell) => cell.text())).toEqual([
        'Category',
        'Blocked',
      ])
    })

    it('counts a series with fewer values than there are categories as nothing for the rest', async () => {
      const { wrapper } = await mountBars({
        stacked: true,
        series: [
          { id: 'low', label: 'Low', values: [5] },
          { id: 'high', label: 'High', values: [3, 2] },
        ],
      })

      expect(values(wrapper)).toEqual(['8', '2'])
      await wrapper.findAll('[data-test="bar-slot"]')[2]?.trigger('pointerenter')
      expect(wrapper.findAll('[data-test="chart-tooltip-row"]').map((row) => row.text())).toEqual([
        '0Low',
        '0High',
        '0Total',
      ])
      await wrapper.find('[data-test="chart-view"]').trigger('click')
      expect(wrapper.findAll('[data-test="chart-table-row"]')[2]?.text()).toBe('printer000')
    })

    it('takes a series out of the chart when it is turned off, and the others keep their colors', async () => {
      const { wrapper } = await mountBars({
        series: [
          { id: 'in', label: 'Received', values: [10, 20, 30] },
          { id: 'out', label: 'Sent', values: [5, 5, 5], icon: Siren },
        ],
      })

      await wrapper.findAll('[data-test="chart-legend-item"]')[0]?.trigger('click')

      const bars = wrapper.findAll('[data-test="bar"]')
      expect(bars).toHaveLength(3)
      expect(bars[0]?.attributes('fill')).toBe('var(--chart-2)')
      // One bar is left of each category, so its value is written again.
      expect(values(wrapper)).toEqual(['5', '5', '5'])
    })

    it('says there is nothing to show when there are no categories or only zeros', async () => {
      const { wrapper } = await mountBars({ categories: [], series: [] })
      expect(wrapper.find('[data-test="chart-empty"]').exists()).toBe(true)
      expect(wrapper.find('[data-test="bar-chart"]').exists()).toBe(false)

      await wrapper.setProps({ categories: ['a'], series: [{ id: 'x', label: 'X', values: [0] }] })
      expect(wrapper.find('[data-test="chart-empty"]').exists()).toBe(true)

      await wrapper.setProps({ series: [{ id: 'x', label: 'X', values: [4] }] })
      expect(wrapper.find('[data-test="bar-chart"]').exists()).toBe(true)
    })

    it('dims the chart while it loads', async () => {
      const { wrapper } = await mountBars({ loading: true })

      expect(wrapper.find('.chart-frame__plot--loading').exists()).toBe(true)
    })

    it('draws at the width it measures', async () => {
      vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(700)
      const { wrapper } = await mountBars()

      expect(wrapper.find('.chart-svg').attributes('width')).toBe('700')
    })

    it('draws at a width of its own until it has measured one', async () => {
      const { wrapper } = await mountBars()

      expect(wrapper.find('.chart-svg').attributes('width')).toBe('480')
    })
  })
})
