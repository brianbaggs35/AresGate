import ChatWriting from '@/components/ChatWriting.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(props: { looked?: { tool: string; summary: string }[]; text?: string }) {
  const { wrapper } = await mountWithPlugins(ChatWriting, {
    props: { looked: props.looked ?? [], text: props.text ?? '' },
  })
  return wrapper
}

describe('ChatWriting', () => {
  it('says it is looking into it until there is something to show', async () => {
    const wrapper = await show({})
    expect(wrapper.find('[data-test="writing-busy"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="writing-text"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="writing-lookups"]').exists()).toBe(false)
  })

  it('shows what has been looked at, and still says it is working', async () => {
    const wrapper = await show({
      looked: [
        { tool: 'open_incidents', summary: '2 open incidents' },
        { tool: 'device', summary: 'device 4' },
      ],
    })
    expect(wrapper.findAll('[data-test="writing-lookup"]').map((chip) => chip.text())).toEqual([
      '2 open incidents',
      'device 4',
    ])
    expect(wrapper.find('[data-test="writing-busy"]').exists()).toBe(true)
  })

  it('shows what has been written, in paragraphs and lists', async () => {
    const wrapper = await show({ text: 'Start with [incident 3].\n- first\n- second' })
    const text = wrapper.find('[data-test="writing-text"]')
    expect(text.text()).toContain('Start with')
    expect(text.findAll('li').map((item) => item.text())).toEqual(['first', 'second'])
    expect(wrapper.find('[data-test="writing-busy"]').exists()).toBe(false)
  })

  it('is not read out word by word', async () => {
    const wrapper = await show({ text: 'Hello' })
    const article = wrapper.find('article')
    expect(article.attributes('aria-live')).toBe('off')
    expect(article.attributes('aria-busy')).toBe('true')
  })
})
