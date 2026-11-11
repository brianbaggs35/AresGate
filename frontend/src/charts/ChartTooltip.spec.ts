import { nextTick } from 'vue'

import ChartTooltip from '@/charts/ChartTooltip.vue'
import { mountWithPlugins } from '@/test/mount'

describe('ChartTooltip', () => {
  const props = {
    x: 120,
    y: 40,
    flip: false,
    heading: 'Oct 26, 6:00 PM',
    rows: [
      { label: 'Download', value: '1,200', color: 'blue', shape: 'line' as const },
      { label: 'Upload', value: '300', color: 'red' },
      { label: 'Total', value: '1,500' },
    ],
  }

  it('says what it points at and each value, the number first', async () => {
    const { wrapper } = await mountWithPlugins(ChartTooltip, { props })

    expect(wrapper.text()).toContain('Oct 26, 6:00 PM')
    const rows = wrapper.findAll('[data-test="chart-tooltip-row"]')
    expect(rows.map((row) => row.text())).toEqual(['1,200Download', '300Upload', '1,500Total'])
    expect(wrapper.findAll('[data-test="chart-tooltip-value"]')).toHaveLength(3)
  })

  it('keys a row with a mark in its color: a line unless it is a square', async () => {
    const { wrapper } = await mountWithPlugins(ChartTooltip, {
      props: {
        ...props,
        rows: [{ ...props.rows[0]!, shape: 'square' }, props.rows[1]!, props.rows[2]!],
      },
    })

    const keys = wrapper.findAll('.chart-tooltip__key')
    expect(keys).toHaveLength(2)
    expect(keys[0]?.classes()).toContain('chart-tooltip__key--square')
    expect(keys[1]?.classes()).toContain('chart-tooltip__key--line')
    expect(keys[1]?.attributes('style')).toContain('--key: red')
  })

  it('sits where it is told, on the right of the point or the left', async () => {
    const { wrapper } = await mountWithPlugins(ChartTooltip, { props })
    const tip = wrapper.find('[data-test="chart-tooltip"]')

    expect(tip.attributes('style')).toContain('left: 120px')
    expect(tip.attributes('style')).toContain('top: 40px')
    expect(tip.classes()).not.toContain('chart-tooltip--flip')

    await wrapper.setProps({ flip: true })
    expect(tip.classes()).toContain('chart-tooltip--flip')
  })

  it('is left out for screen readers, which the chart tells instead', async () => {
    const { wrapper } = await mountWithPlugins(ChartTooltip, { props })

    expect(wrapper.find('[data-test="chart-tooltip"]').attributes('aria-hidden')).toBe('true')
  })

  describe('staying inside the chart', () => {
    /** jsdom lays nothing out, so the sizes the tooltip measures are given: its own height, and
     * the height of the chart's box it is placed in. */
    function laidOut(tooltip: number, box: number) {
      vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(tooltip)
      vi.spyOn(HTMLElement.prototype, 'offsetParent', 'get').mockReturnValue({
        clientHeight: box,
      } as Element)
    }
    const top = (wrapper: Awaited<ReturnType<typeof mountWithPlugins>>['wrapper']) =>
      wrapper.find<HTMLElement>('[data-test="chart-tooltip"]').element.style.top

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('is centred on what it points at when it fits there', async () => {
      laidOut(80, 300)
      const { wrapper } = await mountWithPlugins(ChartTooltip, { props: { ...props, y: 150 } })

      expect(top(wrapper)).toBe('150px')
    })

    it('is moved up so that none of it hangs below the chart, at the foot of an empty column', async () => {
      laidOut(120, 300)
      const { wrapper } = await mountWithPlugins(ChartTooltip, { props: { ...props, y: 290 } })

      // Centred on 290 it would reach down to 350; its centre is at most 300 - 60.
      expect(top(wrapper)).toBe('240px')
    })

    it('is moved down so that none of it is above the chart, at the top of a full column', async () => {
      laidOut(120, 300)
      const { wrapper } = await mountWithPlugins(ChartTooltip, { props: { ...props, y: 10 } })

      expect(top(wrapper)).toBe('60px')
    })

    it('keeps its top in view in a chart too small for all of it', async () => {
      laidOut(200, 100)
      const { wrapper } = await mountWithPlugins(ChartTooltip, { props: { ...props, y: 90 } })

      expect(top(wrapper)).toBe('100px')
    })

    it('fits again when it points somewhere else, or says something else', async () => {
      laidOut(120, 300)
      const { wrapper } = await mountWithPlugins(ChartTooltip, { props: { ...props, y: 290 } })
      expect(top(wrapper)).toBe('240px')

      await wrapper.setProps({ y: 100 })
      await nextTick()
      await nextTick()

      expect(top(wrapper)).toBe('100px')
    })

    it('stays where it is told while the chart has no size to measure', async () => {
      const { wrapper } = await mountWithPlugins(ChartTooltip, { props: { ...props, y: 290 } })

      expect(top(wrapper)).toBe('290px')
    })
  })
})
