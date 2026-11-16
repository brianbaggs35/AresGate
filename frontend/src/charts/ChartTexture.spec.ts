import ChartTexture from '@/charts/ChartTexture.vue'
import { mountWithPlugins } from '@/test/mount'

describe('ChartTexture', () => {
  it('draws a bar or an area as a square carrying the texture class', async () => {
    const { wrapper } = await mountWithPlugins(ChartTexture, {
      props: { texture: 4, shape: 'square', color: 'red' },
    })

    expect(wrapper.find('rect').classes()).toContain('chart-pat-4')
    expect(wrapper.find('line').exists()).toBe(false)
  })

  it('draws a line as a dash in its own color', async () => {
    const { wrapper } = await mountWithPlugins(ChartTexture, {
      props: { texture: 2, shape: 'line', color: 'red' },
    })

    expect(wrapper.find('line').classes()).toContain('chart-dash-2')
    expect(wrapper.find('line').attributes('stroke')).toBe('red')
  })
})
