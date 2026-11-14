import ChatText from '@/components/ChatText.vue'
import { mountWithPlugins } from '@/test/mount'

describe('ChatText', () => {
  it('links the incidents it names and leaves the words alone', async () => {
    const { wrapper } = await mountWithPlugins(ChatText, {
      props: { text: 'Look at [incident 3] soon.' },
    })

    // A component with several roots gives each one's text on its own, so the spaces between them
    // are checked in the page.
    expect(wrapper.element.parentElement?.textContent).toBe('Look at incident 3 soon.')
    const link = wrapper.find('[data-test="message-incident"]')
    expect(link.attributes('href')).toBe('/incidents/3')
  })

  it('links the devices it names to their pages', async () => {
    const { wrapper } = await mountWithPlugins(ChatText, {
      props: { text: 'Is [device 12] the one?' },
    })

    expect(wrapper.element.parentElement?.textContent).toBe('Is device 12 the one?')
    expect(wrapper.find('[data-test="message-device"]').attributes('href')).toBe(
      '/assets/device-12',
    )
  })

  it('is just words when there is no incident in it', async () => {
    const { wrapper } = await mountWithPlugins(ChatText, { props: { text: 'All quiet.' } })

    expect(wrapper.element.parentElement?.textContent).toBe('All quiet.')
    expect(wrapper.find('a').exists()).toBe(false)
  })
})
