import FamilyJudgement from '@/components/FamilyJudgement.vue'
import { mountWithPlugins } from '@/test/mount'
import { familyDetail } from '@/test/threats'

async function show(family = familyDetail(), props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(FamilyJudgement, {
    props: { family, asking: false, failure: null, calling: null, ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('FamilyJudgement', () => {
  it('says what the AI made of the kind, why, and who judged it', async () => {
    const { find } = await show()

    expect(find('judgement-class').text()).toBe('AI: Probe, 92% sure')
    expect(find('judgement-reason').text()).toBe(
      'Internet scanners probing ssh, with nothing open.',
    )
    expect(find('judgement-by').text()).toMatch(/^Judged by Anthropic \(claude-haiku-5-5\) /)
    expect(find('judgement-owner').exists()).toBe(false)
    expect(find('judge').text()).toBe('Ask the AI again')
  })

  it('shows where your review of the judgement stands, and passes on an answer', async () => {
    const { find, wrapper } = await show(familyDetail({ review: 'pending' }))

    expect(find('strip-state').text()).toContain('Waiting for you.')

    wrapper.findComponent({ name: 'ReviewStrip' }).vm.$emit('answered')
    expect(wrapper.emitted('answered')).toHaveLength(1)
  })

  it('has nothing to review before the AI has judged it', async () => {
    const { find } = await show(familyDetail({ classification: null, confidence: null }))

    expect(find('review-strip').exists()).toBe(false)
  })

  it('says how it was judged when the record has no names', async () => {
    const { find } = await show(familyDetail({ provider: null, model: null }))

    expect(find('judgement-by').text()).toMatch(/^Judged by the AI /)
  })

  it('says nothing of when it was judged, when the record does not say', async () => {
    const { find } = await show(familyDetail({ judged_at: null }))

    expect(find('judgement-by').text()).toBe('')
  })

  it('says when no AI has judged it', async () => {
    const { find } = await show(
      familyDetail({ classification: null, confidence: null, reason: null, judged_at: null }),
    )

    expect(find('judgement-none').text()).toContain('No AI has judged this kind yet')
    expect(find('judge').text()).toBe('Ask the AI')
  })

  it('offers both of your words and no way to take one back before you have given it', async () => {
    const { find } = await show()

    expect(find('call-background').text()).toBe('Always background')
    expect(find('call-watch').text()).toBe('Never set aside')
    expect(find('call-clear').exists()).toBe(false)
  })

  it('says your word, disables the one that is given and offers to take it back', async () => {
    const { find } = await show(familyDetail({ owner_call: 'background' }))

    expect(find('judgement-owner').text()).toContain('You set it aside.')
    expect(find('call-background').attributes('disabled')).toBeDefined()
    expect(find('call-watch').attributes('disabled')).toBeUndefined()
    expect(find('call-clear').text()).toBe('Take my word back')
  })

  it('tells the page what you ask for', async () => {
    const { find, wrapper } = await show(familyDetail({ owner_call: 'watch' }))

    await find('call-background').trigger('click')
    await find('call-clear').trigger('click')
    await find('judge').trigger('click')

    expect(wrapper.emitted('call')).toEqual([['background'], [null]])
    expect(wrapper.emitted('ask')).toHaveLength(1)
  })

  it('shows what is under way and holds the other buttons while it is', async () => {
    const { find } = await show(familyDetail({ owner_call: 'watch' }), { calling: 'clear' })

    expect(find('call-clear').classes()).toContain('v-btn--loading')
    expect(find('call-background').attributes('disabled')).toBeDefined()
  })

  it('shows the AI being asked', async () => {
    const { find } = await show(familyDetail(), { asking: true })

    expect(find('judge').classes()).toContain('v-btn--loading')
  })

  it('says why it could not', async () => {
    const { find } = await show(familyDetail(), { failure: 'AI is turned off.' })

    expect(find('judgement-failure').text()).toBe('AI is turned off.')
  })
})
