import { Plug } from '@lucide/vue'

import EmptyState from '@/components/EmptyState.vue'
import { mountWithPlugins } from '@/test/mount'

describe('EmptyState', () => {
  it('says what is missing and what to do about it', async () => {
    const { wrapper } = await mountWithPlugins(EmptyState, {
      props: { title: 'Nothing here yet', description: 'Connect an integration.', icon: Plug },
      slots: { default: '<button data-test="act">Connect</button>' },
    })
    expect(wrapper.find('[data-test="empty-title"]').text()).toBe('Nothing here yet')
    expect(wrapper.find('[data-test="empty-text"]').text()).toBe('Connect an integration.')
    expect(wrapper.find('.empty-state__icon').attributes('aria-hidden')).toBe('true')
    expect(wrapper.find('.empty-state__actions [data-test="act"]').exists()).toBe(true)
  })

  it('can be just a sentence', async () => {
    const { wrapper } = await mountWithPlugins(EmptyState, { props: { title: 'Nothing here' } })
    expect(wrapper.find('[data-test="empty-text"]').exists()).toBe(false)
    expect(wrapper.find('.empty-state__icon').exists()).toBe(false)
    expect(wrapper.find('.empty-state__actions').exists()).toBe(false)
  })
})
