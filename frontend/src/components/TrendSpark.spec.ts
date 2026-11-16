import TrendSpark from '@/components/TrendSpark.vue'
import { mountWithPlugins } from '@/test/mount'

describe('TrendSpark', () => {
  it('draws the shape of the numbers and says what they are in words', async () => {
    const { wrapper } = await mountWithPlugins(TrendSpark, {
      props: { values: [0, 2, 5], label: '7 events in the last 7 days, 5 in the latest.' },
    })

    expect(wrapper.find('[data-test="trend-spark"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="trend-spark-label"]').text()).toBe(
      '7 events in the last 7 days, 5 in the latest.',
    )
  })

  it('shows nothing while there is nothing to draw', async () => {
    const { wrapper } = await mountWithPlugins(TrendSpark, {
      props: { values: [0, 0, 0], label: 'No events.' },
    })

    expect(wrapper.find('[data-test="trend-spark"]').exists()).toBe(false)
  })
})
