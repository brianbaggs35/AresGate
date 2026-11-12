import * as reviewApi from '@/api/review'
import { ApiError } from '@/api/client'
import ReviewAnswer from '@/components/ReviewAnswer.vue'
import { decision } from '@/test/review'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(props: Record<string, unknown> = {}) {
  const answer = vi
    .spyOn(reviewApi, 'answerDecision')
    .mockResolvedValue(decision({ review: 'agreed' }))
  const mounted = await mountWithPlugins(ReviewAnswer, {
    signedIn: 'admin',
    props: { subject: 'family', id: 7, kind: 'probe', review: 'pending', ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, answer, find }
}

describe('ReviewAnswer', () => {
  it('agrees, and tells the page what the server answered', async () => {
    const { wrapper, find, answer } = await open()

    await find('review-agree').trigger('click')
    await flushPromises()

    expect(answer).toHaveBeenCalledWith('family', 7, 'agree', null, false, 'a-security-token')
    expect(wrapper.emitted('answered')?.[0]).toEqual([decision({ review: 'agreed' })])
  })

  it('disagrees with a reason, trimmed, and starts again afterwards', async () => {
    const { find, answer } = await open()

    await find('review-add-reason').trigger('click')
    await find('review-reason').find('textarea').setValue('  That is my camera  ')
    await find('review-disagree').trigger('click')
    await flushPromises()

    expect(answer).toHaveBeenCalledWith(
      'family',
      7,
      'disagree',
      'That is my camera',
      false,
      'a-security-token',
    )
    expect(find('review-reason').exists()).toBe(false)
  })

  it('can keep a kind that was set aside, and says so to the server', async () => {
    const { find, answer } = await open()

    await find('review-keep').find('input').setValue(true)
    await find('review-agree').trigger('click')
    await flushPromises()

    expect(answer).toHaveBeenCalledWith('family', 7, 'agree', null, true, 'a-security-token')
  })

  it('has nothing to keep for one incident, or for an alarm', async () => {
    expect((await open({ subject: 'incident' })).find('review-keep').exists()).toBe(false)
    expect((await open({ kind: 'attack' })).find('review-keep').exists()).toBe(false)
  })

  it('shows what was said, with the reason, and takes it back', async () => {
    const { wrapper, find, answer } = await open({
      review: 'disagreed',
      said: 'Not a probe',
    })

    expect(find('review-said').text()).toBe('You disagreed. “Not a probe”')
    expect(find('review-agree').exists()).toBe(false)

    await find('review-undo').trigger('click')
    await flushPromises()

    expect(answer).toHaveBeenCalledWith('family', 7, 'undo', null, false, 'a-security-token')
    expect(wrapper.emitted('answered')).toHaveLength(1)
  })

  it('shows an agreement without a reason', async () => {
    const { find } = await open({ review: 'agreed' })

    expect(find('review-said').text()).toBe('You agreed.')
  })

  it('says when it could not be sent, and does not tell the page', async () => {
    const { wrapper, find, answer } = await open()
    answer.mockRejectedValue(new ApiError(500, 'Could not save.', 'server'))

    await find('review-agree').trigger('click')
    await flushPromises()

    expect(find('review-failure').text()).toBe('Could not save.')
    expect(wrapper.emitted('answered')).toBeUndefined()
  })
})
