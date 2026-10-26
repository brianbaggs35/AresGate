import { Siren } from '@lucide/vue'

import ChartLegend from '@/charts/ChartLegend.vue'
import type { LegendItem } from '@/charts/types'
import { mountWithPlugins } from '@/test/mount'

const items: LegendItem[] = [
  { id: 'a', label: 'Received', color: 'red', shape: 'square' },
  { id: 'b', label: 'Sent', color: 'blue', shape: 'line', icon: Siren },
  { id: 'c', label: 'Dropped', color: 'green', shape: 'square' },
]

describe('ChartLegend', () => {
  it('names each series with its color, and an icon where it has one', async () => {
    const { wrapper } = await mountWithPlugins(ChartLegend, { props: { items, hidden: [] } })

    expect(
      wrapper.findAll('[data-test="chart-legend-label"]').map((label) => label.text()),
    ).toEqual(['Received', 'Sent', 'Dropped'])
    const keys = wrapper.findAll('.chart-legend__key')
    expect(keys[0]?.classes()).toContain('chart-legend__key--square')
    expect(keys[0]?.attributes('style')).toContain('--key: red')
    expect(keys[1]?.classes()).toContain('chart-legend__key--line')
    expect(wrapper.findAll('.v-icon')).toHaveLength(1)
    expect(wrapper.find('ul').attributes('aria-label')).toBe('Series')
  })

  it('shows which series are on, as buttons that are pressed or not', async () => {
    const { wrapper } = await mountWithPlugins(ChartLegend, { props: { items, hidden: ['b'] } })

    const buttons = wrapper.findAll('button')
    expect(buttons.map((button) => button.attributes('aria-pressed'))).toEqual([
      'true',
      'false',
      'true',
    ])
    expect(buttons[1]?.classes()).toContain('chart-legend__item--off')
  })

  it('turns a series off and on again', async () => {
    const { wrapper } = await mountWithPlugins(ChartLegend, { props: { items, hidden: [] } })

    await wrapper.findAll('button')[1]?.trigger('click')
    expect(wrapper.emitted('update:hidden')).toEqual([[['b']]])

    await wrapper.setProps({ hidden: ['b', 'c'] })
    await wrapper.findAll('button')[1]?.trigger('click')
    expect(wrapper.emitted('update:hidden')?.[1]).toEqual([['c']])
  })

  it('never turns the last series off', async () => {
    const { wrapper } = await mountWithPlugins(ChartLegend, {
      props: { items, hidden: ['a', 'b'] },
    })

    await wrapper.findAll('button')[2]?.trigger('click')

    expect(wrapper.emitted('update:hidden')).toBeUndefined()
  })
})
