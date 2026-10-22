import ThemeToggle from '@/components/ThemeToggle.vue'
import { useThemeStore } from '@/stores/theme'
import { flushPromises, mountWithPlugins } from '@/test/mount'

describe('ThemeToggle', () => {
  it('labels the button with the current preference', async () => {
    const { wrapper } = await mountWithPlugins(ThemeToggle)
    expect(wrapper.find('[data-test="theme-toggle"]').attributes('aria-label')).toBe(
      'Theme: System',
    )
    wrapper.unmount()
  })

  it('switches the theme from the menu', async () => {
    const { wrapper } = await mountWithPlugins(ThemeToggle)
    await wrapper.find('[data-test="theme-toggle"]').trigger('click')
    await flushPromises()
    const dark = document.querySelector<HTMLElement>('[data-test="theme-dark"]')!
    dark.click()
    await flushPromises()
    expect(useThemeStore().preference).toBe('dark')
    expect(wrapper.find('[data-test="theme-toggle"]').attributes('aria-label')).toBe('Theme: Dark')
    wrapper.unmount()
  })
})
