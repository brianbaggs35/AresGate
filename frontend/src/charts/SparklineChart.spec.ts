import SparklineChart from '@/charts/SparklineChart.vue'
import { mountWithPlugins } from '@/test/mount'

function mountSpark(props: Record<string, unknown> = {}) {
  return mountWithPlugins(SparklineChart, {
    props: { label: 'Blocked per hour, now 31', values: [8, 12, 9, 22, 31], ...props },
  })
}

describe('SparklineChart', () => {
  it('draws the shape of the values, and says in words what it shows', async () => {
    const { wrapper } = await mountSpark()

    const image = wrapper.find('svg')
    expect(image.attributes('role')).toBe('img')
    expect(image.attributes('aria-label')).toBe('Blocked per hour, now 31')
    const path = wrapper.find('path').attributes('d') ?? ''
    expect(path.startsWith('M0,')).toBe(true)
    expect(path.match(/L/g)).toHaveLength(4)
    expect(wrapper.find('path').attributes('stroke-width')).toBe('2')
  })

  it('runs from its own lowest to its own highest, high values up', async () => {
    const { wrapper } = await mountSpark({ values: [0, 10], height: 32 })

    // 6 of room above and below in 32: the lowest is at 26, the highest at 6.
    expect(wrapper.find('path').attributes('d')).toBe('M0,26L100,6')
  })

  it('puts the latest reading in a dot of the given color, at the end of the line', async () => {
    const { wrapper } = await mountSpark({ color: 'rgb(1, 2, 3)', values: [0, 10] })

    const dot = wrapper.find('[data-test="sparkline-dot"]')
    expect(dot.attributes('style')).toContain('left: 100%')
    expect(dot.attributes('style')).toContain('top: 6px')
    expect(dot.attributes('style')).toContain('background: rgb(1, 2, 3)')
  })

  it('uses the first hue unless it is given a color', async () => {
    const { wrapper } = await mountSpark()

    expect(wrapper.find('[data-test="sparkline-dot"]').attributes('style')).toContain(
      'background: var(--chart-1)',
    )
  })

  it('ends at the last reading there is, and breaks where nothing was measured', async () => {
    const { wrapper } = await mountSpark({ values: [1, null, 3, 5, null] })

    expect(wrapper.find('path').attributes('d')?.match(/M/g)).toHaveLength(2)
    expect(wrapper.find('[data-test="sparkline-dot"]').attributes('style')).toContain('left: 75%')
  })

  it('puts a lone value in the middle, and a flat run of them half way up', async () => {
    const single = await mountSpark({ values: [4] })
    expect(single.wrapper.find('[data-test="sparkline-dot"]').attributes('style')).toContain(
      'left: 50%',
    )
    expect(single.wrapper.find('[data-test="sparkline-dot"]').attributes('style')).toContain(
      'top: 16px',
    )

    const flat = await mountSpark({ values: [3, 3, 3] })
    expect(flat.wrapper.find('path').attributes('d')).toBe('M0,16L50,16L100,16')
  })

  it('draws nothing but its room, still described, when there is nothing to draw', async () => {
    const { wrapper } = await mountSpark({ values: [null, null] })

    expect(wrapper.find('path').exists()).toBe(false)
    expect(wrapper.find('[data-test="sparkline-dot"]').exists()).toBe(false)
    expect(wrapper.find('svg').attributes('aria-label')).toBe('Blocked per hour, now 31')
    expect(wrapper.attributes('style')).toContain('height: 32px')
  })
})
