import DiscordText from '@/components/DiscordText.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(text: string) {
  return mountWithPlugins(DiscordText, { props: { text } })
}

describe('DiscordText', () => {
  it('draws a line of words as a paragraph', async () => {
    const { wrapper } = await show('Just words')

    const lines = wrapper.findAll('[data-test="discord-line"]')
    expect(lines).toHaveLength(1)
    expect(lines[0]!.text()).toBe('Just words')
  })

  it('draws bold, code and the words of a link as what they are', async () => {
    const { wrapper } = await show('A **bold** `code` [link](https://x.example/y)')

    expect(wrapper.find('strong').text()).toBe('bold')
    expect(wrapper.find('code').text()).toBe('code')
    expect(wrapper.find('.text__link').text()).toBe('link')
    expect(wrapper.find('a').exists()).toBe(false)
  })

  it('keeps a gap between paragraphs as an empty line', async () => {
    const { wrapper } = await show('One\n\nTwo')

    const lines = wrapper.findAll('[data-test="discord-line"]')
    expect(lines.map((line) => line.text())).toEqual(['One', '', 'Two'])
  })

  it('never takes text for markup', async () => {
    const { wrapper } = await show('<img src=x onerror=alert(1)> <b>not bold</b>')

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('b').exists()).toBe(false)
    expect(wrapper.text()).toContain('<b>not bold</b>')
  })
})
