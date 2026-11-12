import ReviewNudge from '@/components/ReviewNudge.vue'
import { useReviewStore } from '@/stores/review'
import { mountWithPlugins } from '@/test/mount'

async function open(waiting: number) {
  return mountWithPlugins(ReviewNudge, {
    withApp: true,
    beforeMount: () => {
      useReviewStore().set(waiting)
    },
  })
}

describe('ReviewNudge', () => {
  it('is not there when nothing waits', async () => {
    const { wrapper } = await open(0)

    expect(wrapper.find('[data-test="review-nudge"]').exists()).toBe(false)
  })

  it('says how many wait, and opens the page', async () => {
    const { wrapper } = await open(4)

    expect(wrapper.find('[data-test="review-nudge-text"]').text()).toBe(
      'The AI has decided 4 things that wait for you to agree or disagree.',
    )
    expect(wrapper.find('[data-test="review-nudge-open"]').attributes('href')).toBe('/review')
  })

  it('speaks of one in the singular', async () => {
    const { wrapper } = await open(1)

    expect(wrapper.find('[data-test="review-nudge-text"]').text()).toBe(
      'The AI has decided 1 thing that waits for you to agree or disagree.',
    )
  })
})
