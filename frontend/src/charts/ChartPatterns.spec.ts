import ChartPatterns from '@/charts/ChartPatterns.vue'
import { mountWithPlugins } from '@/test/mount'

describe('ChartPatterns', () => {
  it('defines the eight textures once, out of sight of a screen reader', async () => {
    const { wrapper } = await mountWithPlugins(ChartPatterns)

    const patterns = wrapper.findAll('pattern')
    expect(patterns.map((pattern) => pattern.attributes('id'))).toEqual(
      Array.from({ length: 8 }, (_, index) => `chart-pattern-${(index + 1).toString()}`),
    )
    expect(wrapper.find('svg').attributes('aria-hidden')).toBe('true')
  })
})
