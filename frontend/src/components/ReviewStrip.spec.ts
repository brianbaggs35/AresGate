import ReviewStrip from '@/components/ReviewStrip.vue'
import { mountWithPlugins } from '@/test/mount'

async function open(props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(ReviewStrip, {
    signedIn: 'admin',
    props: { subject: 'incident', id: 4, kind: 'probe', review: 'pending', ...props },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, find }
}

describe('ReviewStrip', () => {
  it('says where the review stands, and offers the answer', async () => {
    const { find } = await open()

    expect(find('strip-state').text()).toContain('Waiting for you.')
    expect(find('review-agree').exists()).toBe(true)
  })

  it('shows an answered one without the buttons to answer', async () => {
    const { find } = await open({ review: 'agreed' })

    expect(find('strip-state').text()).toContain('You agreed.')
    expect(find('review-agree').exists()).toBe(false)
  })

  it('has nothing to review when the AI could not tell', async () => {
    const { find } = await open({ kind: 'unclear', review: 'auto' })

    expect(find('review-strip').exists()).toBe(false)
  })

  it('tells the page when it was answered', async () => {
    const { wrapper } = await open()
    wrapper.findComponent({ name: 'ReviewAnswer' }).vm.$emit('answered', {})

    expect(wrapper.emitted('answered')).toHaveLength(1)
  })
})
