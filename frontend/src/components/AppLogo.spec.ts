import AppLogo from '@/components/AppLogo.vue'
import { mountWithPlugins } from '@/test/mount'

describe('AppLogo', () => {
  it('shows the mark beside the name, which a screen reader reads as one word', async () => {
    const { wrapper } = await mountWithPlugins(AppLogo)
    expect(wrapper.find('img').attributes('alt')).toBe('')
    expect(wrapper.text()).toBe('AresGate')
    expect(wrapper.find('.text-brand').text()).toBe('Gate')
  })

  it('sizes the mark', async () => {
    const { wrapper } = await mountWithPlugins(AppLogo)
    expect(wrapper.find('img').attributes('width')).toBe('36')
    await wrapper.setProps({ size: 48 })
    expect(wrapper.find('img').attributes('height')).toBe('48')
  })

  it('can show the mark alone', async () => {
    const { wrapper } = await mountWithPlugins(AppLogo, { props: { compact: true } })
    expect(wrapper.find('img').exists()).toBe(true)
    expect(wrapper.text()).toBe('')
  })
})
