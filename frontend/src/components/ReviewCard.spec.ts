import ReviewCard from '@/components/ReviewCard.vue'
import { decision } from '@/test/review'
import { mountWithPlugins } from '@/test/mount'

async function open(item = decision()) {
  const mounted = await mountWithPlugins(ReviewCard, {
    signedIn: 'admin',
    props: { decision: item },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('ReviewCard', () => {
  it('says what the AI called it, how sure and why', async () => {
    const { find, wrapper } = await open()

    expect(find('review-kind').text()).toBe('Probe')
    expect(find('review-confidence').text()).toBe('92% sure')
    expect(find('review-why').text()).toBe('Internet scanners probing ssh, with nothing open.')
    expect(find('review-state').text()).toBe('Waiting for you')
    expect(find('review-by').text()).toContain('Anthropic (claude-haiku-5-5)')
    expect(wrapper.find('[data-test="review-card"]').attributes('data-kind')).toBe('probe')
  })

  it('says what it does if you agree, or that it counts already', async () => {
    expect((await open()).find('review-effect').text()).toBe(
      'If you agree: Sets aside 41 incidents going on, and any more of this kind.',
    )
    const counting = await open(
      decision({ review: 'auto', counting: true, effect: 'Raises 2 incidents going on.' }),
    )
    expect(counting.find('review-effect').text()).toBe('It counts: Raises 2 incidents going on.')
  })

  it('links a kind to its page and an incident to its own', async () => {
    const kind = await open()
    expect(kind.find('review-link').attributes('href')).toBe('/threats/kinds/7')
    expect(kind.find('review-scope').text()).toBe('A kind of incident, 41 incidents')

    const one = await open(
      decision({ subject: 'incident', id: 9, incidents: 1, provider: null, model: null }),
    )
    expect(one.find('review-link').attributes('href')).toBe('/incidents/9')
    expect(one.find('review-scope').text()).toBe('One incident')
    expect(one.find('review-by').text()).toContain('The AI,')

    const single = await open(decision({ incidents: 1 }))
    expect(single.find('review-scope').text()).toBe('A kind of incident, 1 incident')
  })

  it('passes on an answer', async () => {
    const { wrapper } = await open()
    wrapper.findComponent({ name: 'ReviewAnswer' }).vm.$emit('answered', decision())

    expect(wrapper.emitted('answered')).toHaveLength(1)
  })
})
