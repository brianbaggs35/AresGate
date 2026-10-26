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
})
