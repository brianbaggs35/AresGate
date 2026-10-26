import { nextTick } from 'vue'

import HeatmapChart from '@/charts/HeatmapChart.vue'
import { mountWithPlugins } from '@/test/mount'

const rows = ['Mon', 'Tue']
const columns = ['0', '6', '12', '18']
const values = [
  [0, 5, 10, 50],
  [1, 0, 25, 3],
]

function mountMap(props: Record<string, unknown> = {}) {
  return mountWithPlugins(HeatmapChart, {
    props: { title: 'When alerts happen', rows, columns, values, unit: 'alerts', ...props },
  })
}

/** jsdom has no pointer events, so a mouse event goes by the name. */
function point(element: Element, type: string, pointerType = 'mouse') {
  const event = new MouseEvent(type, { bubbles: true })
  Object.assign(event, { pointerType })
  element.dispatchEvent(event)
  return nextTick()
}

describe('HeatmapChart', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('draws a cell for each row and column, named along the sides', async () => {
    const { wrapper } = await mountMap()

    expect(wrapper.findAll('[data-test="heatmap-cell"]')).toHaveLength(8)
    expect(wrapper.findAll('[data-test="heatmap-row"]').map((row) => row.text())).toEqual(rows)
    expect(wrapper.findAll('[data-test="heatmap-column"]').map((name) => name.text())).toEqual(
      columns,
    )
    expect(wrapper.find('[data-test="chart-legend"]').exists()).toBe(false)
  })

  it('shades a cell by how much it has on five steps, and a cell with nothing is flat gray', async () => {
    const { wrapper } = await mountMap()

    const fills = wrapper
      .findAll('[data-test="heatmap-cell"]')
      .map((cell) => cell.attributes('fill'))
    expect(fills).toEqual([
      'var(--chart-empty)',
      'var(--chart-step-1)',
      'var(--chart-step-1)',
      'var(--chart-step-5)',
      'var(--chart-step-1)',
      'var(--chart-empty)',
      'var(--chart-step-3)',
      'var(--chart-step-1)',
    ])
  })

  it('shows the scale, from none to the most', async () => {
    const { wrapper } = await mountMap({ format: (value: number) => `${value.toString()}!` })

    const scale = wrapper.find('[data-test="heatmap-scale"]')
    expect(scale.text()).toBe('None50!')
    expect(scale.findAll('.heatmap__swatch')).toHaveLength(6)
  })

  it('names only some of a crowded set of columns', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(200)
    const names = Array.from({ length: 24 }, (_, hour) => `${hour.toString().padStart(2, '0')}:00`)
    const { wrapper } = await mountMap({
      columns: names,
      values: [names.map((_, index) => index), names.map(() => 1)],
    })

    const shown = wrapper
      .findAll('[data-test="heatmap-column"]')
      .filter((name) => name.attributes('display') !== 'none')
    expect(shown.length).toBeGreaterThan(0)
    expect(shown.length).toBeLessThan(24)
    expect(shown[0]?.text()).toBe('00:00')
  })

  it('keeps its cells big enough to touch, and scrolls rather than squeeze them', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(200)
    const names = Array.from({ length: 24 }, (_, hour) => hour.toString())
    const { wrapper } = await mountMap({
      columns: names,
      values: [names.map(() => 1), names.map(() => 1)],
    })

    const cell = wrapper.find('[data-test="heatmap-cell"]')
    expect(Number(cell.attributes('width'))).toBeGreaterThanOrEqual(22)
    expect(Number(wrapper.find('.chart-svg').attributes('width'))).toBeGreaterThan(200)
  })

  describe('reading it', () => {
    it('says what a cell holds when it is pointed at, and puts it away when the pointer leaves', async () => {
      const { wrapper } = await mountMap()
      const cells = wrapper.findAll('[data-test="heatmap-cell"]')

      await point(cells[3]!.element, 'pointerenter')

      const tip = wrapper.find('[data-test="chart-tooltip"]')
      expect(tip.text()).toContain('Mon · 18')
      expect(tip.find('[data-test="chart-tooltip-row"]').text()).toBe('50alerts')
      expect(wrapper.find('[role="status"]').text()).toBe('Mon · 18: 50 alerts')
      expect(cells[3]?.classes()).toContain('heatmap__cell--active')
      expect(cells[0]?.classes()).not.toContain('heatmap__cell--active')

      await point(wrapper.find('.chart-svg').element, 'pointerleave')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
      expect(wrapper.find('[role="status"]').text()).toBe('')
    })

    it('opens the tooltip on the left over the right half, and writes values as told', async () => {
      const { wrapper } = await mountMap({
        format: (value: number) => `${value.toString()} per day`,
      })
      const cells = wrapper.findAll('[data-test="heatmap-cell"]')

      await point(cells[0]!.element, 'pointerdown')
      expect(wrapper.find('[data-test="chart-tooltip"]').classes()).not.toContain(
        'chart-tooltip--flip',
      )
      await point(cells[7]!.element, 'pointerenter')
      expect(wrapper.find('[data-test="chart-tooltip"]').classes()).toContain('chart-tooltip--flip')
      expect(wrapper.find('[data-test="chart-tooltip-row"]').text()).toBe('3 per dayalerts')
    })

    it('keeps what a finger touched until it touches something else', async () => {
      const { wrapper } = await mountMap()

      await point(wrapper.findAll('[data-test="heatmap-cell"]')[1]!.element, 'pointerdown')
      await point(wrapper.find('.chart-svg').element, 'pointerleave', 'touch')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(true)

      await wrapper.find('.chart-svg').trigger('blur')
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)
    })

    it('moves across and down the grid with the arrow keys, and stops at the edges', async () => {
      const { wrapper } = await mountMap()
      const chart = wrapper.find('.chart-svg')
      const at = () => wrapper.find('[role="status"]').text()

      await chart.trigger('keydown', { key: 'ArrowRight' })
      expect(at()).toBe('Mon · 0: 0 alerts')
      await chart.trigger('keydown', { key: 'ArrowRight' })
      expect(at()).toBe('Mon · 6: 5 alerts')
      await chart.trigger('keydown', { key: 'ArrowDown' })
      expect(at()).toBe('Tue · 6: 0 alerts')
      await chart.trigger('keydown', { key: 'ArrowDown' })
      expect(at()).toBe('Tue · 6: 0 alerts')
      await chart.trigger('keydown', { key: 'ArrowLeft' })
      await chart.trigger('keydown', { key: 'ArrowLeft' })
      expect(at()).toBe('Tue · 0: 1 alerts')
      await chart.trigger('keydown', { key: 'ArrowUp' })
      await chart.trigger('keydown', { key: 'ArrowUp' })
      expect(at()).toBe('Mon · 0: 0 alerts')
      await chart.trigger('keydown', { key: 'End' })
      expect(at()).toBe('Mon · 18: 50 alerts')
      await chart.trigger('keydown', { key: 'ArrowRight' })
      expect(at()).toBe('Mon · 18: 50 alerts')
      await chart.trigger('keydown', { key: 'Home' })
      expect(at()).toBe('Mon · 0: 0 alerts')
    })

    it('starts from the end or the start when an arrow is the first key', async () => {
      const first = await mountMap()
      await first.wrapper.find('.chart-svg').trigger('keydown', { key: 'ArrowLeft' })
      expect(first.wrapper.find('[role="status"]').text()).toBe('Mon · 0: 0 alerts')

      const second = await mountMap()
      await second.wrapper.find('.chart-svg').trigger('keydown', { key: 'End' })
      expect(second.wrapper.find('[role="status"]').text()).toBe('Mon · 18: 50 alerts')

      const third = await mountMap()
      await third.wrapper.find('.chart-svg').trigger('keydown', { key: 'ArrowUp' })
      expect(third.wrapper.find('[role="status"]').text()).toBe('Mon · 0: 0 alerts')
    })

    it('puts the readout away with Escape, and leaves the other keys to the page', async () => {
      const { wrapper } = await mountMap()
      const chart = wrapper.find('.chart-svg')

      await chart.trigger('keydown', { key: 'Home' })
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(true)
      await chart.trigger('keydown', { key: 'Escape' })
      expect(wrapper.find('[data-test="chart-tooltip"]').exists()).toBe(false)

      const event = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true })
      chart.element.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(false)
      expect(chart.attributes('tabindex')).toBe('0')
      expect(chart.attributes('role')).toBe('img')
    })

    it('points the tooltip at the cell even when the grid is scrolled sideways', async () => {
      const { wrapper } = await mountMap()
      const scroller = wrapper.find('.heatmap__scroll').element
      Object.defineProperty(scroller, 'scrollLeft', { configurable: true, value: 40 })

      await point(wrapper.findAll('[data-test="heatmap-cell"]')[1]!.element, 'pointerenter')
      const scrolled = wrapper.find('[data-test="chart-tooltip"]').attributes('style')
      Object.defineProperty(scroller, 'scrollLeft', { configurable: true, value: 0 })
      await point(wrapper.findAll('[data-test="heatmap-cell"]')[2]!.element, 'pointerenter')
      await point(wrapper.findAll('[data-test="heatmap-cell"]')[1]!.element, 'pointerenter')
      const unscrolled = wrapper.find('[data-test="chart-tooltip"]').attributes('style')

      const left = (style?: string) => Number(/left: ([\d.]+)px/.exec(style ?? '')?.[1])
      expect(left(unscrolled) - left(scrolled)).toBe(40)
    })
  })

  describe('as a table and in its other states', () => {
    it('lists every cell, row by row', async () => {
      const { wrapper } = await mountMap({ rowLabel: 'Day' })

      await wrapper.find('[data-test="chart-view"]').trigger('click')

      expect(wrapper.findAll('thead th').map((cell) => cell.text())).toEqual(['Day', ...columns])
      const body = wrapper.findAll('[data-test="chart-table-row"]')
      expect(body[0]?.findAll('td').map((cell) => cell.text())).toEqual(['0', '5', '10', '50'])
      expect(body[1]?.find('th').text()).toBe('Tue')
    })

    it('says there is nothing to show with no rows, no columns or only zeros', async () => {
      const { wrapper } = await mountMap({ rows: [], values: [] })
      expect(wrapper.find('[data-test="chart-empty"]').exists()).toBe(true)

      await wrapper.setProps({ rows, columns: [], values: [[], []] })
      expect(wrapper.find('[data-test="chart-empty"]').exists()).toBe(true)

      await wrapper.setProps({ columns, values: [[0, 0, 0, 0], []] })
      expect(wrapper.find('[data-test="chart-empty"]').exists()).toBe(true)
    })

    it('treats a row with fewer values than columns as nothing for the rest', async () => {
      const { wrapper } = await mountMap({ values: [[1], []] })

      const fills = wrapper
        .findAll('[data-test="heatmap-cell"]')
        .map((cell) => cell.attributes('fill'))
      expect(fills[0]).toBe('var(--chart-step-5)')
      expect(fills.slice(1)).toEqual(new Array<string>(7).fill('var(--chart-empty)'))
    })

    it('dims while it loads', async () => {
      const { wrapper } = await mountMap({ loading: true })

      expect(wrapper.find('.chart-frame__plot--loading').exists()).toBe(true)
    })
  })
})
