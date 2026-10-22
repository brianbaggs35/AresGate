import App from '@/App.vue'
import { useThemeStore } from '@/stores/theme'
import { flushPromises, mountWithPlugins } from '@/test/mount'

describe('App', () => {
  it('shows the app bar, the menu at the side and the page for the route', async () => {
    const { wrapper } = await mountWithPlugins(App, { route: '/', width: 1280 })
    await flushPromises()
    expect(wrapper.find('[data-test="page-title"]').text()).toBe('Overview')
    expect(wrapper.find('.app-drawer').exists()).toBe(true)
    expect(wrapper.find('.v-bottom-navigation').exists()).toBe(false)
    expect(wrapper.find('[data-test="theme-toggle"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="status-card"]').exists()).toBe(true)
  })

  it('puts the menu at the bottom on a phone', async () => {
    const { wrapper } = await mountWithPlugins(App, { route: '/', width: 400 })
    await flushPromises()
    expect(wrapper.find('.app-drawer').exists()).toBe(false)
    expect(wrapper.find('.v-bottom-navigation').exists()).toBe(true)
    expect(wrapper.text()).toContain('AresGate')
  })

  it('lets the keyboard skip the menu', async () => {
    const { wrapper } = await mountWithPlugins(App, { route: '/', width: 1280 })
    await flushPromises()
    const link = wrapper.find('[data-test="skip-link"]')
    expect(link.text()).toBe('Skip to the page')
    await link.trigger('click')
    expect(document.activeElement?.id).toBe('main-content')
    expect(window.location.hash).toBe('')
  })

  it('applies the theme preference to Vuetify', async () => {
    const { wrapper, vuetify } = await mountWithPlugins(App, { route: '/' })
    useThemeStore().setPreference('dark')
    await flushPromises()
    expect(vuetify.theme.name.value).toBe('dark')
    expect(wrapper.find('.v-theme--dark').exists()).toBe(true)
  })
})
