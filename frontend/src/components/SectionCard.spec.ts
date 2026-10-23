import { defineComponent, h, ref } from 'vue'

import SectionCard from '@/components/SectionCard.vue'
import { mountWithPlugins } from '@/test/mount'

describe('SectionCard', () => {
  it('has a title, what it is for, and the content', async () => {
    const { wrapper } = await mountWithPlugins(SectionCard, {
      props: { title: 'Passkeys', description: 'Sign in with your device.' },
      slots: { default: '<p data-test="body">Content</p>' },
    })
    expect(wrapper.find('h2').text()).toBe('Passkeys')
    expect(wrapper.find('[data-test="section-description"]').text()).toBe(
      'Sign in with your device.',
    )
    expect(wrapper.find('[data-test="body"]').text()).toBe('Content')
  })

  it('leaves out a description and actions it has none of', async () => {
    const { wrapper } = await mountWithPlugins(SectionCard, { props: { title: 'Passkeys' } })
    expect(wrapper.find('[data-test="section-description"]').exists()).toBe(false)
    expect(wrapper.find('.section-card__actions').exists()).toBe(false)
  })

  it('puts the actions for the whole card beside the title', async () => {
    const { wrapper } = await mountWithPlugins(SectionCard, {
      props: { title: 'Activity' },
      slots: { actions: '<button data-test="refresh">Refresh</button>' },
    })
    expect(wrapper.find('.section-card__actions [data-test="refresh"]').exists()).toBe(true)
  })

  it('moves the keyboard to its title on request', async () => {
    const card = ref<{ focusTitle: () => void } | null>(null)
    const Page = defineComponent({
      render: () => h(SectionCard, { ref: card, title: 'Passkeys' }),
    })
    const { wrapper } = await mountWithPlugins(Page)

    card.value?.focusTitle()

    expect(document.activeElement).toBe(wrapper.find('h2').element)
  })
})
