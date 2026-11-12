import { ApiError } from '@/api/client'
import * as reviewApi from '@/api/review'
import { useReviewStore } from '@/stores/review'
import { decision, reviewPage } from '@/test/review'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import ReviewView from '@/views/ReviewView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(first: reviewApi.ReviewPage | Error = reviewPage()) {
  const fetchIt = vi.spyOn(reviewApi, 'fetchReview')
  if (first instanceof Error) fetchIt.mockRejectedValue(first)
  else fetchIt.mockResolvedValue(first)
  const agreeAll = vi.spyOn(reviewApi, 'agreeWith').mockResolvedValue({ agreed: 2 })
  const mounted = await mountWithPlugins(ReviewView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const cards = () => mounted.wrapper.findAll('[data-test="review-card"]')
  return { ...mounted, fetchIt, agreeAll, find, cards }
}

const two = () =>
  reviewPage({
    total: 2,
    items: [
      decision(),
      decision({ subject: 'incident', id: 9, kind: 'attack', title: 'An attack' }),
    ],
    counts: { waiting: 2, decided: 0, answered: 0 },
  })

describe('ReviewView', () => {
  it('shows a placeholder while it asks, and says when it could not', async () => {
    vi.spyOn(reviewApi, 'fetchReview').mockReturnValue(new Promise(() => {}))
    const loading = await mountWithPlugins(ReviewView, { signedIn: 'admin' })
    expect(loading.wrapper.find('[data-test="review-loading"]').exists()).toBe(true)

    const failed = await open(offline())
    expect(failed.find('review-error').text()).toContain("Can't reach AresGate.")
  })

  it('asks again every minute, keeping what it shows', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const { fetchIt, cards } = await open()
      fetchIt.mockClear()

      vi.advanceTimersByTime(60_000)
      await flushPromises()

      expect(fetchIt).toHaveBeenCalledWith('waiting', 20)
      expect(cards()).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('tries again from the error', async () => {
    const { find, fetchIt, cards } = await open(offline())
    fetchIt.mockResolvedValue(reviewPage())

    await find('retry').trigger('click')
    await flushPromises()

    expect(find('review-error').exists()).toBe(false)
    expect(cards()).toHaveLength(1)
  })

  it('drops the answer to a question that was asked before another', async () => {
    const { fetchIt, wrapper, cards } = await open()
    let late: (page: reviewApi.ReviewPage) => void = () => {}
    fetchIt.mockReturnValueOnce(
      new Promise((resolve) => {
        late = resolve
      }),
    )
    fetchIt.mockResolvedValue(reviewPage({ state: 'answered', total: 0, items: [] }))

    wrapper.findComponent({ name: 'ReviewCard' }).vm.$emit('answered', decision())
    await flushPromises()
    await wrapper.find('[data-test="review-list-answered"]').trigger('click')
    await flushPromises()
    late(reviewPage({ items: [decision(), decision({ id: 8 })] }))
    await flushPromises()

    expect(cards()).toHaveLength(0)
  })

  it('drops the failure of a question that was asked before another', async () => {
    const { fetchIt, wrapper, find } = await open()
    let late: (error: Error) => void = () => {}
    fetchIt.mockReturnValueOnce(
      new Promise((_, reject) => {
        late = reject
      }),
    )
    fetchIt.mockResolvedValue(reviewPage({ state: 'answered', total: 0, items: [] }))

    wrapper.findComponent({ name: 'ReviewCard' }).vm.$emit('answered', decision())
    await flushPromises()
    await wrapper.find('[data-test="review-list-answered"]').trigger('click')
    await flushPromises()
    late(offline())
    await flushPromises()

    expect(find('review-stale').exists()).toBe(false)
  })

  it('does not agree with everything when the question is put away', async () => {
    const { find, agreeAll } = await open(two())

    await find('review-agree-all').trigger('click')
    await flushPromises()
    document.querySelector<HTMLElement>('[data-test="confirm-cancel"]')?.click()
    await flushPromises()

    expect(agreeAll).not.toHaveBeenCalled()
  })

  it('lists what waits, with how many are in each list, and tells the menu', async () => {
    const { cards, find, wrapper, pinia } = await open()

    expect(cards()).toHaveLength(1)
    expect(wrapper.find('[data-test="review-list-waiting"]').text()).toBe('Waiting 1')
    expect(wrapper.find('[data-test="review-list-decided"]').text()).toBe('Decided for you 2')
    expect(wrapper.find('[data-test="review-list-answered"]').text()).toBe('Answered 3')
    expect(find('review-settings').attributes('href')).toBe('/settings/review')
    expect(useReviewStore(pinia).waiting).toBe(1)
  })

  it('says all is done when nothing waits, and what each other list holds', async () => {
    const { find, fetchIt, wrapper } = await open(reviewPage({ total: 0, items: [] }))
    expect(find('review-empty').text()).toContain('All caught up')

    fetchIt.mockResolvedValue(reviewPage({ state: 'answered', total: 0, items: [] }))
    await wrapper.find('[data-test="review-list-answered"]').trigger('click')
    await flushPromises()

    expect(fetchIt).toHaveBeenLastCalledWith('answered', 20)
    expect(find('review-empty').text()).toContain('You have not answered anything yet.')
  })

  it('takes an answered decision out and asks for the counts again', async () => {
    const { cards, fetchIt, find } = await open(two())
    fetchIt.mockResolvedValue(
      reviewPage({
        total: 1,
        items: [decision({ subject: 'incident', id: 9 })],
        counts: { waiting: 1, decided: 0, answered: 1 },
      }),
    )
    vi.spyOn(reviewApi, 'answerDecision').mockResolvedValue(decision({ review: 'agreed' }))

    await cards()[0]?.find('[data-test="review-agree"]').trigger('click')
    await flushPromises()

    expect(cards()).toHaveLength(1)
    expect(fetchIt).toHaveBeenLastCalledWith('waiting', 20)
    expect(find('review-notice').exists()).toBe(false)
  })

  it('agrees with everything shown, after asking', async () => {
    const { find, agreeAll, fetchIt } = await open(two())

    await find('review-agree-all').trigger('click')
    await flushPromises()
    expect(agreeAll).not.toHaveBeenCalled()

    fetchIt.mockResolvedValue(reviewPage({ total: 0, items: [] }))
    document.querySelector<HTMLElement>('[data-test="confirm-accept"]')?.click()
    await flushPromises()

    expect(agreeAll).toHaveBeenCalledWith(
      [
        { subject: 'family', id: 7 },
        { subject: 'incident', id: 9 },
      ],
      'a-security-token',
    )
    expect(find('review-notice').text()).toBe('You agreed with 2 decisions.')
  })

  it('says it agreed with one decision in the singular', async () => {
    const { find, agreeAll } = await open(two())
    agreeAll.mockResolvedValue({ agreed: 1 })

    await find('review-agree-all').trigger('click')
    document.querySelector<HTMLElement>('[data-test="confirm-accept"]')?.click()
    await flushPromises()

    expect(find('review-notice').text()).toBe('You agreed with 1 decision.')
  })

  it('says when agreeing with all failed', async () => {
    const { find, agreeAll } = await open(two())
    agreeAll.mockRejectedValue(new ApiError(500, 'Could not save.', 'server'))

    await find('review-agree-all').trigger('click')
    document.querySelector<HTMLElement>('[data-test="confirm-accept"]')?.click()
    await flushPromises()

    expect(find('review-action-failure').text()).toBe('Could not save.')
  })

  it('offers no agree-all for one decision, or outside the waiting list', async () => {
    const one = await open()
    expect(one.find('review-agree-all').exists()).toBe(false)

    const decided = await open(reviewPage({ state: 'waiting', total: 2, items: two().items }))
    decided.fetchIt.mockResolvedValue(
      reviewPage({ state: 'decided', total: 2, items: two().items }),
    )
    await decided.wrapper.find('[data-test="review-list-decided"]').trigger('click')
    await flushPromises()
    expect(decided.find('review-agree-all').exists()).toBe(false)
  })

  it('shows more when there are more', async () => {
    const { find, fetchIt, cards } = await open(reviewPage({ total: 25 }))
    expect(find('review-more').text()).toBe('Show 20 more (24 left)')
    fetchIt.mockResolvedValue(
      reviewPage({ total: 25, items: [decision({ id: 8 }), decision({ id: 10 })] }),
    )

    await find('review-more').trigger('click')
    await flushPromises()

    expect(fetchIt).toHaveBeenLastCalledWith('waiting', 20, 1)
    expect(cards()).toHaveLength(3)
  })

  it('says when showing more failed', async () => {
    const { find, fetchIt } = await open(reviewPage({ total: 25 }))
    fetchIt.mockRejectedValue(offline())

    await find('review-more').trigger('click')
    await flushPromises()

    expect(find('review-action-failure').text()).toContain("Can't reach AresGate.")
  })

  it('says how much the owner agrees with the AI, with a bar', async () => {
    const { find } = await open(
      reviewPage({
        standing: {
          agreed: 9,
          disagreed: 1,
          rate: 0.9,
          trusted: false,
          trust_after: 20,
          trust_rate: 0.95,
        },
      }),
    )

    expect(find('review-standing-line').text()).toContain(
      'You agreed with 9 of 10 decisions (90%).',
    )
    expect(find('review-offer').exists()).toBe(false)
  })

  it('offers to let the AI decide on its own once it has earned it', async () => {
    const trusted = {
      agreed: 30,
      disagreed: 0,
      rate: 1,
      trusted: true,
      trust_after: 20,
      trust_rate: 0.95,
    }
    const { find } = await open(reviewPage({ standing: trusted }))
    expect(find('review-offer').attributes('href')).toBe('/settings/review')

    const already = await open(reviewPage({ standing: trusted, mode: 'auto' }))
    expect(already.find('review-offer').exists()).toBe(false)
  })

  it('keeps what it shows when asking again fails', async () => {
    const { find, fetchIt, cards, wrapper } = await open()
    fetchIt.mockRejectedValue(offline())

    await wrapper.findComponent({ name: 'ReviewCard' }).vm.$emit('answered', decision())
    await flushPromises()

    expect(find('review-stale').text()).toContain('What is shown is from earlier.')
    expect(cards()).toHaveLength(0)
  })
})
