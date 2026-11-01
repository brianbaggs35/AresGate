import ChatConversations from '@/components/ChatConversations.vue'
import { summary } from '@/test/aiChat'
import { mountWithPlugins } from '@/test/mount'

async function show(current: number | null = null, conversations = [summary()]) {
  const mounted = await mountWithPlugins(ChatConversations, { props: { conversations, current } })
  return mounted
}

describe('ChatConversations', () => {
  it('says there are none yet', async () => {
    const { wrapper } = await show(null, [])

    expect(wrapper.find('[data-test="conversations-empty"]').text()).toContain('Nothing asked yet')
    expect(wrapper.find('[data-test="conversation"]').exists()).toBe(false)
  })

  it('lists each with a link to open it', async () => {
    const { wrapper } = await show(null, [
      summary({ id: 5, title: 'First' }),
      summary({ id: 6, title: 'Second' }),
    ])

    const links = wrapper.findAll('[data-test="conversation-link"]')
    expect(links.map((link) => link.text())).toEqual([
      expect.stringContaining('First'),
      expect.stringContaining('Second'),
    ])
    expect(links.map((link) => link.attributes('href'))).toEqual(['/assistant/5', '/assistant/6'])
  })

  it('marks the one that is open', async () => {
    const { wrapper } = await show(5, [summary({ id: 5 }), summary({ id: 6 })])

    const links = wrapper.findAll('[data-test="conversation-link"]')
    expect(links[0]?.attributes('aria-current')).toBe('page')
    expect(links[1]?.attributes('aria-current')).toBeUndefined()
  })

  it('asks to delete the one whose button was pressed', async () => {
    const { wrapper } = await show(null, [summary({ id: 5, title: 'First' })])
    const button = wrapper.find('[data-test="conversation-delete"]')

    expect(button.attributes('aria-label')).toBe('Delete the conversation First')
    await button.trigger('click')

    expect(wrapper.emitted('delete')).toEqual([[summary({ id: 5, title: 'First' })]])
  })
})
