import { Siren } from '@lucide/vue'
import type { VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'

import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import type { ChartMark } from '@/charts/types'
import { formatDateTime } from '@/format'
import { mountWithPlugins } from '@/test/mount'

const HOUR = 3_600_000
const start = new Date(2026, 9, 26, 0, 0).getTime()
/** Twenty-five readings an hour apart: a day. */
const times = Array.from({ length: 25 }, (_, index) => start + index * HOUR)
const down = times.map((_, index) => 100 + index * 20)
const up = times.map((_, index) => 10 + index)

function mountLines(props: Record<string, unknown> = {}) {
  return mountWithPlugins(TimeSeriesChart, {
    props: {
      title: 'Throughput',
      times,
      series: [{ id: 'down', label: 'Download', values: down }],
      ...props,
    },
  })
}

describe('TimeSeriesChart', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('drawing', () => {
    it('draws a line for each series in its own color, over a grid from zero and a time axis', async () => {
      const { wrapper } = await mountLines({
        series: [
          { id: 'down', label: 'Download', values: down },
          { id: 'up', label: 'Upload', values: up },
        ],
      })

      const lines = wrapper.findAll('[data-test="line"]')
      expect(lines.map((line) => line.attributes('stroke'))).toEqual([
        'var(--chart-1)',
        'var(--chart-2)',
      ])
      expect(lines[0]?.attributes('stroke-width')).toBe('2')
      expect(lines[0]?.attributes('d')?.startsWith('M')).toBe(true)
      expect(wrapper.findAll('.chart-grid').length).toBeGreaterThan(2)
      expect(wrapper.find('.chart-axis').exists()).toBe(true)
      expect(wrapper.findAll('[data-test="time-tick"]').length).toBeGreaterThan(2)
      expect(wrapper.findAll('[data-test="chart-legend-item"]')).toHaveLength(2)
    })

    it('washes the area under a line when asked', async () => {
      const { wrapper } = await mountLines()
      expect(wrapper.find('[fill-opacity]').exists()).toBe(false)

      await wrapper.setProps({ area: true })
      expect(wrapper.find('[fill-opacity="0.1"]').exists()).toBe(true)
    })

    it('breaks a line where nothing was measured instead of dropping to zero', async () => {
      const gappy = down.map((value, index) => (index > 8 && index < 14 ? null : value))
      const { wrapper } = await mountLines({
        series: [{ id: 'down', label: 'Download', values: gappy }],
      })

      expect(wrapper.find('[data-test="line"]').attributes('d')?.match(/M/g)).toHaveLength(2)
    })

    it('ends a line with a dot, and its last value written beside it', async () => {
      const { wrapper } = await mountLines({
        format: (value: number) => `${value.toString()} Mb/s`,
      })

      expect(wrapper.findAll('[data-test="end-dot"]')).toHaveLength(1)
      expect(wrapper.find('[data-test="end-value"]').text()).toBe('580 Mb/s')
    })

    it('puts the dot at the last reading there is', async () => {
      const { wrapper } = await mountLines({
        series: [
          { id: 'down', label: 'Download', values: down.map((v, i) => (i === 24 ? null : v)) },
          { id: 'nothing', label: 'Nothing', values: times.map(() => null) },
        ],
      })

      expect(wrapper.findAll('[data-test="end-dot"]')).toHaveLength(1)
      expect(wrapper.find('[data-test="end-value"]').text()).toBe('560')
    })

    it('leaves the end values off when the lines end too close for them to be clear', async () => {
      const { wrapper } = await mountLines({
        series: [
          { id: 'down', label: 'Download', values: down },
          { id: 'up', label: 'Upload', values: down.map((value) => value - 1) },
        ],
      })

      expect(wrapper.findAll('[data-test="end-dot"]')).toHaveLength(2)
      expect(wrapper.findAll('[data-test="end-value"]')).toHaveLength(0)
    })

    it('leaves the end values off a narrow chart, and from a crowd of lines', async () => {
      vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(360)
      const narrow = await mountLines()
      expect(narrow.wrapper.find('[data-test="end-value"]').exists()).toBe(false)

      vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(900)
      const crowd = await mountLines({
        series: [1, 2, 3, 4, 5].map((n) => ({
          id: `s${n.toString()}`,
          label: `Series ${n.toString()}`,
          values: down.map((value) => value * n),
        })),
      })
      expect(crowd.wrapper.find('[data-test="end-value"]').exists()).toBe(false)
      expect(crowd.wrapper.findAll('[data-test="end-dot"]')).toHaveLength(5)
    })

    it('draws a flat chart of zeros, which is still something that was measured', async () => {
      const { wrapper } = await mountLines({
        series: [{ id: 'down', label: 'Download', values: times.map(() => 0) }],
      })

      expect(wrapper.find('[data-test="chart-empty"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="line"]').exists()).toBe(true)
    })

    it('draws a single reading as a dot', async () => {
      const { wrapper } = await mountLines({
        times: [start],
        series: [{ id: 'down', label: 'Download', values: [5] }],
      })

      expect(wrapper.find('[data-test="line"]').attributes('d')).toMatch(
        /^M[\d.]+,[\d.]+L[\d.]+,[\d.]+$/,
      )
      expect(wrapper.find('[data-test="end-dot"]').exists()).toBe(true)
    })

    it('says there is nothing to show with no readings or only gaps', async () => {
      const { wrapper } = await mountLines({ times: [], series: [] })
      expect(wrapper.find('[data-test="chart-empty"]').exists()).toBe(true)

      await wrapper.setProps({
        times,
        series: [{ id: 'down', label: 'Download', values: times.map(() => null) }],
      })
      expect(wrapper.find('[data-test="chart-empty"]').exists()).toBe(true)
    })
  })

  describe('reading it', () => {
    const both = {
      series: [
        { id: 'down', label: 'Download', values: down },
        {
          id: 'up',
          label: 'Upload',
          values: up.map((value, index) => (index === 12 ? null : value)),
        },
      ],
    }

    /** jsdom has no pointer events with positions, so this is a mouse event under the name. */
    function pointer(chart: Element, type: string, clientX: number, pointerType = 'mouse') {
      const event = new MouseEvent(type, { clientX, bubbles: true })
      Object.assign(event, { pointerType })
      chart.dispatchEvent(event)
      return nextTick()
    }

    /** Where the plot starts across the chart, from its first gridline, and how long it is. */
    async function geometry() {
      const { wrapper } = await mountLines(both)
      const chart = wrapper.find('.chart-svg').element
      const left = Number(wrapper.find('.chart-grid').attributes('x1'))
      await pointer(chart, 'pointermove', left + 100_000)
      const length = Number(wrapper.find('[data-test="crosshair"]').attributes('x1'))
      return { wrapper, chart, left, length }
    }

    it('reads every line at the moment under the pointer', async () => {
      const { wrapper, chart, left } = await geometry()
      expect(wrapper.find('[data-test="end-dot"]').exists()).toBe(false)

      await pointer(chart, 'pointermove', left - 50)

      expect(wrapper.find('[data-test="crosshair"]').attributes('x1')).toBe('0')
      expect(wrapper.findAll('[data-test="dot"]')).toHaveLength(2)
      const tip = wrapper.find('[data-test="chart-tooltip"]')
      expect(tip.text()).toContain('Oct 26, 2026, 12:00 AM')
      expect(tip.findAll('[data-test="chart-tooltip-row"]').map((row) => row.text())).toEqual([
        '100Download',
        '10Upload',
      ])
      expect(wrapper.find('output').text()).toBe('Oct 26, 2026, 12:00 AM: 100 Download, 10 Upload')
    })

    it('has no readout until it is pointed at, and brings the end dots back when it is put away', async () => {
      const { wrapper } = await mountLines(both)
      expect(wrapper.find('[data-test="crosshair"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
      expect(wrapper.findAll('[data-test="end-dot"]')).toHaveLength(2)
    })

    it('snaps to the nearest moment', async () => {
      const { wrapper, chart, left, length } = await geometry()

      // Half way along is the thirteenth reading of twenty-five; a little either side of it too.
      for (const nudge of [-3, 0, 3]) {
        await pointer(chart, 'pointermove', left + length / 2 + nudge)
        expect(Number(wrapper.find('[data-test="crosshair"]').attributes('x1'))).toBeCloseTo(
          length / 2,
          1,
        )
      }
      await pointer(chart, 'pointermove', left + (length * 3.4) / 24)
      expect(Number(wrapper.find('[data-test="crosshair"]').attributes('x1'))).toBeCloseTo(
        (length * 3) / 24,
        1,
      )
    })

    it('says where there is no data, and keeps the dots to the lines that have a value', async () => {
      const { wrapper, chart, left, length } = await geometry()

      await pointer(chart, 'pointermove', left + length / 2)

      expect(wrapper.findAll('[data-test="chart-tooltip-row"]').map((row) => row.text())).toEqual([
        '340Download',
        'No dataUpload',
      ])
      expect(wrapper.findAll('[data-test="dot"]')).toHaveLength(1)
    })

    it('opens the tooltip on the left in the right half of the chart', async () => {
      const { wrapper, chart, left, length } = await geometry()

      await pointer(chart, 'pointermove', left)
      expect(wrapper.find('[data-test="chart-tooltip"]').classes()).not.toContain(
        'chart-tooltip--flip',
      )
      await pointer(chart, 'pointermove', left + length)
      expect(wrapper.find('[data-test="chart-tooltip"]').classes()).toContain('chart-tooltip--flip')
    })

    it('points at the middle of the plot when no line has a value at that moment', async () => {
      const { wrapper } = await mountLines({
        series: [
          {
            id: 'down',
            label: 'Download',
            values: down.map((value, index) => (index === 0 ? null : value)),
          },
        ],
      })

      await wrapper.find('.chart-svg').trigger('keydown', { key: 'Home' })

      expect(wrapper.findAll('[data-test="dot"]')).toHaveLength(0)
      expect(wrapper.find('[data-test="chart-tooltip-row"]').text()).toBe('No dataDownload')
    })

    it('puts the readout away when the pointer leaves, but not when a finger lifts', async () => {
      const { wrapper, chart, left } = await geometry()

      await pointer(chart, 'pointermove', left, 'touch')
      await pointer(chart, 'pointerleave', 0, 'touch')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(true)

      await pointer(chart, 'pointerleave', 0, 'mouse')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
    })

    it('also reads where a finger or a click goes down', async () => {
      const { wrapper, chart, left } = await geometry()

      await pointer(chart, 'pointerdown', left, 'touch')

      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(true)
    })

    it('goes through the moments with the keys, and puts the readout away with Escape or on leaving', async () => {
      const { wrapper } = await mountLines(both)
      const chart = wrapper.find('.chart-svg')

      await chart.trigger('keydown', { key: 'End' })
      expect(wrapper.find('output').text()).toBe('Oct 27, 2026, 12:00 AM: 580 Download, 34 Upload')
      await chart.trigger('keydown', { key: 'ArrowLeft' })
      expect(wrapper.find('output').text()).toContain('Oct 26, 2026, 11:00 PM')
      await chart.trigger('keydown', { key: 'Escape' })
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)

      await chart.trigger('keydown', { key: 'Home' })
      await chart.trigger('blur')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
    })

    it('leaves the other keys to the page, and can be reached with the keyboard', async () => {
      const { wrapper } = await mountLines(both)
      const chart = wrapper.find('.chart-svg')
      const event = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true })

      chart.element.dispatchEvent(event)

      expect(event.defaultPrevented).toBe(false)
      expect(chart.attributes('tabindex')).toBe('0')
      expect(chart.attributes('role')).toBe('img')
      expect(chart.attributes('aria-label')).toContain('Throughput')
    })
  })

  describe('as a table, with a line turned off', () => {
    it('lists every moment with each series, and says where there is no data', async () => {
      const { wrapper } = await mountLines({
        series: [
          { id: 'down', label: 'Download', values: down },
          {
            id: 'up',
            label: 'Upload',
            values: up.map((value, index) => (index === 0 ? null : value)),
          },
        ],
      })

      await wrapper.find('[data-test="chart-view"]').trigger('click')

      expect(wrapper.findAll('thead th').map((cell) => cell.text())).toEqual([
        'Time',
        'Download',
        'Upload',
      ])
      const rows = wrapper.findAll('[data-test="chart-table-row"]')
      expect(rows).toHaveLength(25)
      expect(rows[0]?.findAll('td').map((cell) => cell.text())).toEqual(['100', 'No data'])
    })

    it('takes a line out when it is turned off and rescales to what is left', async () => {
      const { wrapper } = await mountLines({
        series: [
          { id: 'down', label: 'Download', values: down },
          { id: 'up', label: 'Upload', values: up },
        ],
      })
      const before = wrapper.findAll('.chart-text').map((text) => text.text())

      await wrapper.findAll('[data-test="chart-legend-item"]')[0]?.trigger('click')

      expect(wrapper.findAll('[data-test="line"]')).toHaveLength(1)
      expect(wrapper.find('[data-test="line"]').attributes('stroke')).toBe('var(--chart-2)')
      expect(wrapper.findAll('.chart-text').map((text) => text.text())).not.toEqual(before)
    })

    it('dims while it loads', async () => {
      const { wrapper } = await mountLines({ loading: true })

      expect(wrapper.find('.chart-frame__plot--loading').exists()).toBe(true)
    })
  })

  describe('marks', () => {
    const mark = (id: number, hours: number, changes: Partial<ChartMark> = {}): ChartMark => ({
      id: `incident-${id.toString()}`,
      time: start + hours * HOUR,
      weight: id,
      label: `Incident ${id.toString()}`,
      heading: `Began at hour ${hours.toString()}`,
      rows: [{ value: 'High', label: `About ${id.toString()}`, color: 'red' }],
      color: 'red',
      icon: Siren,
      to: { name: 'incident', params: { id } },
      ...changes,
    })
    const flagsOf = (wrapper: VueWrapper) => wrapper.findAll('[data-test="chart-flag"]')

    it('flags each one above the chart, on a line down to when it began, and links to it', async () => {
      const { wrapper } = await mountLines({ marks: [mark(7, 6), mark(9, 18)] })

      expect(wrapper.find('[data-test="chart-flags"]').attributes('aria-label')).toBe(
        'Incidents in this time',
      )
      const flags = flagsOf(wrapper)
      expect(flags.map((flag) => flag.attributes('href'))).toEqual(['/incidents/7', '/incidents/9'])
      expect(flags.map((flag) => flag.attributes('aria-label'))).toEqual([
        'Incident 7',
        'Incident 9',
      ])
      expect(wrapper.findAll('[data-test="chart-flag-line"]')).toHaveLength(2)
      expect(wrapper.find('[data-test="chart-flag-count"]').exists()).toBe(false)
      // Later is further along.
      const lefts = wrapper
        .findAll('.time-series__flag')
        .map((flag) =>
          Number.parseFloat(flag.attributes('style')?.match(/left: ([\d.]+)px/)?.[1] ?? ''),
        )
      expect(lefts[1]).toBeGreaterThan(lefts[0] as number)
    })

    it('makes room above the plot for them, and only when there are some', async () => {
      const without = await mountLines()
      const withMarks = await mountLines({ marks: [mark(7, 6)] })
      const top = (wrapper: VueWrapper) =>
        wrapper
          .find('g[transform]')
          .attributes('transform')
          ?.match(/,([\d.]+)\)/)?.[1]

      expect(without.wrapper.find('[data-test="chart-flags"]').exists()).toBe(false)
      expect(Number(top(withMarks.wrapper))).toBeGreaterThan(Number(top(without.wrapper)))
    })

    it('keeps one that is outside the time of the chart at its nearest end', async () => {
      const { wrapper } = await mountLines({ marks: [mark(1, -30), mark(2, 90)] })

      const lines = wrapper.findAll('[data-test="chart-flag-line"]')
      expect(lines[0]?.attributes('x1')).toBe('0')
      expect(Number(lines[1]?.attributes('x1'))).toBeGreaterThan(300)
    })

    it('draws those too close to tell apart as one flag that says how many it stands for', async () => {
      const { wrapper } = await mountLines({
        marks: [mark(1, 6), mark(2, 6.5, { weight: 50 }), mark(3, 7)],
      })

      const [flag, ...others] = flagsOf(wrapper)
      expect(others).toHaveLength(0)
      expect(wrapper.find('[data-test="chart-flag-count"]').text()).toBe('3')
      // It says the one that matters most, and where that leads.
      expect(flag?.attributes('aria-label')).toBe(
        '3 incidents close together, the most serious first: Incident 2',
      )
      expect(flag?.attributes('href')).toBe('/incidents/2')
    })

    it('reads out an incident when it is pointed at or focused, and not after', async () => {
      const { wrapper } = await mountLines({ marks: [mark(7, 6), mark(9, 18)] })
      const flags = flagsOf(wrapper)
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)

      await flags[1]?.trigger('pointerenter')
      expect(wrapper.find('.chart-tooltip__heading').text()).toBe('Began at hour 18')
      expect(wrapper.find('[data-test="chart-tooltip-row"]').text()).toContain('About 9')
      await flags[1]?.trigger('pointerleave')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)

      await flags[0]?.trigger('focus')
      expect(wrapper.find('.chart-tooltip__heading').text()).toBe('Began at hour 6')
      await flags[0]?.trigger('blur')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
    })

    it('opens the readout of a flag on the right to the left, and of one on the left to the right', async () => {
      const { wrapper } = await mountLines({ marks: [mark(7, 2), mark(9, 23)] })
      const [early, late] = flagsOf(wrapper)

      await early?.trigger('pointerenter')
      expect(wrapper.find('.chart-tooltip--flip').exists()).toBe(false)
      await late?.trigger('pointerenter')
      expect(wrapper.find('.chart-tooltip--flip').exists()).toBe(true)
    })

    it('lists the first of those a flag stands for in its readout, and how many more there are', async () => {
      const { wrapper } = await mountLines({
        marks: [1, 2, 3, 4, 5, 6].map((id) => mark(id, 6 + id / 100, { weight: id })),
      })

      await flagsOf(wrapper)[0]?.trigger('pointerenter')

      expect(wrapper.find('.chart-tooltip__heading').text()).toBe(
        `6 incidents around ${formatDateTime(new Date(start + 6.06 * HOUR).toISOString())}`,
      )
      const rows = wrapper.findAll('[data-test="chart-tooltip-row"]').map((row) => row.text())
      expect(rows).toHaveLength(5)
      expect(rows[0]).toContain('About 6')
      expect(rows.at(-1)).toContain('and 2 more')
    })

    it('does not add a line to the readout for six, but lists three as they are', async () => {
      const { wrapper } = await mountLines({
        marks: [1, 2, 3].map((id) => mark(id, 6 + id / 100, { weight: id })),
      })

      await flagsOf(wrapper)[0]?.trigger('pointerenter')

      const rows = wrapper.findAll('[data-test="chart-tooltip-row"]').map((row) => row.text())
      expect(rows).toHaveLength(3)
      expect(rows.join(' ')).not.toContain('more')
    })

    it('stops reading out a flag that is not there any more', async () => {
      const { wrapper } = await mountLines({ marks: [mark(7, 6)] })
      await flagsOf(wrapper)[0]?.trigger('pointerenter')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(true)

      await wrapper.setProps({ marks: [] })

      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
    })

    it('lists them in the table, with the reading each began in', async () => {
      const { wrapper } = await mountLines({ marks: [mark(7, 6.5), mark(9, 18)] })

      await wrapper.find('[data-test="chart-view"]').trigger('click')

      expect(wrapper.findAll('thead th').map((cell) => cell.text())).toEqual([
        'Time',
        'Download',
        'Incidents',
      ])
      const rows = wrapper
        .findAll('[data-test="chart-table-row"]')
        .map((row) => row.findAll('td').at(-1)?.text())
      expect(rows[6]).toBe('Incident 7')
      expect(rows[18]).toBe('Incident 9')
      expect(rows[0]).toBe('None')
    })

    it('has no column of incidents when there are none', async () => {
      const { wrapper } = await mountLines()

      await wrapper.find('[data-test="chart-view"]').trigger('click')

      expect(wrapper.findAll('thead th').map((cell) => cell.text())).toEqual(['Time', 'Download'])
    })

    it('flags nothing on a chart that has nothing to show', async () => {
      const { wrapper } = await mountLines({ series: [], marks: [mark(7, 6)] })

      expect(wrapper.find('[data-test="chart-flags"]').exists()).toBe(false)
    })
  })
})
