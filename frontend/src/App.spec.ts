import App from '@/App.vue'
import { useThemeStore } from '@/stores/theme'
import { flushPromises, mountWithPlugins } from '@/test/mount'

describe('App', () => {
  it('shows the app bar and the page for the route', async () => {
    const { wrapper } = await mountWithPlugins(App, { route: '/' })
    await flushPromises()
    expect(wrapper.text()).toContain('AresGate')
    expect(wrapper.find('[data-test="theme-toggle"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="status-card"]').exists()).toBe(true)
  })

  it('applies the theme preference to Vuetify', async () => {
    const { wrapper, vuetify } = await mountWithPlugins(App, { route: '/' })
    useThemeStore().setPreference('dark')
    await flushPromises()
    expect(vuetify.theme.name.value).toBe('dark')
    expect(wrapper.find('.v-theme--dark').exists()).toBe(true)
  })
})
