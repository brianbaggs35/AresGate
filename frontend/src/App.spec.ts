import * as authApi from '@/api/auth'
import { ApiError } from '@/api/client'
import * as collectorsApi from '@/api/collectors'
import * as dashboardApi from '@/api/dashboard'
import App from '@/App.vue'
import { guardRoutes } from '@/router/guard'
import { usePaletteStore } from '@/stores/palette'
import { useSessionStore } from '@/stores/session'
import { useThemeStore } from '@/stores/theme'
import { report } from '@/test/collectors'
import { dashboard } from '@/test/dashboard'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const signedIn = { route: '/', signedIn: 'admin' }

describe('App', () => {
  it('shows the app bar, the menu at the side and the page for the route', async () => {
    vi.spyOn(dashboardApi, 'fetchDashboard').mockResolvedValue(dashboard())
    vi.spyOn(collectorsApi, 'fetchCollectors').mockResolvedValue(report())
    const { wrapper } = await mountWithPlugins(App, { ...signedIn, width: 1280 })
    await flushPromises()
    expect(wrapper.find('[data-test="page-title"]').text()).toBe('Dashboard')
    expect(wrapper.find('.app-drawer').exists()).toBe(true)
    expect(wrapper.find('.v-bottom-navigation').exists()).toBe(false)
    expect(wrapper.find('[data-test="theme-toggle"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-menu"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="posture"]').exists()).toBe(true)
  })

  it('puts the menu at the bottom on a phone', async () => {
    const { wrapper } = await mountWithPlugins(App, { ...signedIn, width: 400 })
    await flushPromises()
    expect(wrapper.find('.app-drawer').exists()).toBe(false)
    expect(wrapper.find('.v-bottom-navigation').exists()).toBe(true)
    expect(wrapper.text()).toContain('AresGate')
  })

  it('shows the sign-in page on its own, with no menu', async () => {
    const { wrapper } = await mountWithPlugins(App, { route: '/sign-in', width: 1280 })
    await flushPromises()
    expect(wrapper.find('[data-test="auth-card"]').exists()).toBe(true)
    expect(wrapper.find('.app-drawer').exists()).toBe(false)
    expect(wrapper.find('.v-app-bar').exists()).toBe(false)
  })

  it('shows no menu on a phone either before anyone has signed in', async () => {
    const { wrapper } = await mountWithPlugins(App, { route: '/sign-in', width: 400 })
    await flushPromises()
    expect(wrapper.find('.v-bottom-navigation').exists()).toBe(false)
  })

  it('lets the keyboard skip the menu', async () => {
    const { wrapper } = await mountWithPlugins(App, { ...signedIn, width: 1280 })
    await flushPromises()
    const link = wrapper.find('[data-test="skip-link"]')
    expect(link.text()).toBe('Skip to the page')
    await link.trigger('click')
    expect(document.activeElement?.id).toBe('main-content')
    expect(window.location.hash).toBe('')
  })

  it('applies the theme preference to Vuetify', async () => {
    const { wrapper, vuetify } = await mountWithPlugins(App, signedIn)
    useThemeStore().setPreference('dark')
    await flushPromises()
    expect(vuetify.theme.name.value).toBe('dark')
    expect(wrapper.find('.v-theme--dark').exists()).toBe(true)
  })

  it('goes to the sign-in page, and on from there, when the sign-in ends', async () => {
    const { router } = await mountWithPlugins(App, {
      route: '/settings/account',
      signedIn: 'admin',
    })
    await flushPromises()
    const session = useSessionStore()
    session.expired = true
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('sign-in')
    })
    expect(router.currentRoute.value.query).toEqual({ next: '/settings/account' })

    // Signing in again isn't a reason to move.
    session.expired = false
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('sign-in')
  })

  describe('the shortcut for the command palette', () => {
    const press = (init: KeyboardEventInit) => {
      const event = new KeyboardEvent('keydown', { key: 'k', cancelable: true, ...init })
      window.dispatchEvent(event)
      return event
    }

    it('opens with Ctrl and K, and closes with them again', async () => {
      await mountWithPlugins(App, { ...signedIn, width: 1280 })
      await flushPromises()
      const palette = usePaletteStore()

      // The browser's own use of the keys, to search the web, is left out of it.
      expect(press({ ctrlKey: true }).defaultPrevented).toBe(true)
      expect(palette.open).toBe(true)
      await flushPromises()
      expect(document.querySelector('[data-test="palette"]')).not.toBeNull()

      press({ ctrlKey: true })
      expect(palette.open).toBe(false)
    })

    it('closes with Escape, as dialogs do, and the palette is told', async () => {
      await mountWithPlugins(App, { ...signedIn, width: 1280 })
      await flushPromises()
      const palette = usePaletteStore()
      palette.open = true
      await vi.waitFor(() => {
        expect(document.querySelector('[data-test="palette"]')).not.toBeNull()
      })

      // The dialog answers Escape once it is the top one, which it is a moment after it opens.
      await vi.waitFor(() => {
        document
          .querySelector('[data-test="palette"]')!
          .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
        expect(palette.open).toBe(false)
      })
    })

    it('opens with ⌘ and K, in either case', async () => {
      await mountWithPlugins(App, { ...signedIn, width: 1280 })
      await flushPromises()

      press({ metaKey: true, key: 'K' })

      expect(usePaletteStore().open).toBe(true)
    })

    it('leaves K on its own, and the other keys with Ctrl, alone', async () => {
      await mountWithPlugins(App, { ...signedIn, width: 1280 })
      await flushPromises()

      expect(press({}).defaultPrevented).toBe(false)
      expect(press({ ctrlKey: true, key: 'j' }).defaultPrevented).toBe(false)
      expect(usePaletteStore().open).toBe(false)
    })

    it('is for someone who is signed in', async () => {
      await mountWithPlugins(App, { route: '/sign-in', width: 1280 })
      await flushPromises()

      expect(press({ ctrlKey: true }).defaultPrevented).toBe(false)
      expect(usePaletteStore().open).toBe(false)
    })

    it('is put away when the person signs out', async () => {
      await mountWithPlugins(App, { ...signedIn, width: 1280 })
      await flushPromises()
      const palette = usePaletteStore()
      palette.open = true
      await flushPromises()

      useSessionStore().username = null
      await flushPromises()

      expect(palette.open).toBe(false)
    })

    it('stops listening when the app is taken away', async () => {
      const { wrapper } = await mountWithPlugins(App, { ...signedIn, width: 1280 })
      await flushPromises()
      wrapper.unmount()

      expect(press({ ctrlKey: true }).defaultPrevented).toBe(false)
    })
  })

  describe('when the API can’t say who is signed in', () => {
    const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

    it('says so, and tries again on request', async () => {
      const setup = vi.spyOn(authApi, 'fetchSetupRequired').mockRejectedValueOnce(offline())
      setup.mockResolvedValue(false)
      vi.spyOn(authApi, 'fetchSession').mockResolvedValue({
        username: 'admin',
        csrf_token: 'a-token',
        expires_at: '2026-01-01T12:00:00Z',
      })
      const { wrapper, router } = await mountWithPlugins(App, { width: 1280 })
      guardRoutes(router)
      await router.push('/settings/account?tab=activity')
      await flushPromises()
      expect(wrapper.find('[data-test="startup-error"]').text()).toContain("Can't reach AresGate.")
      expect(wrapper.find('.app-drawer').exists()).toBe(false)

      const replace = vi.spyOn(router, 'replace')
      await wrapper.find('[data-test="retry"]').trigger('click')
      await flushPromises()
      // The retry ends when it has gone back to the page, so wait for that to be over.
      await replace.mock.results[0]?.value
      await flushPromises()
      expect(wrapper.find('[data-test="startup-error"]').exists()).toBe(false)
      expect(router.currentRoute.value.fullPath).toBe('/settings/account?tab=activity')
      expect(wrapper.find('.app-drawer').exists()).toBe(true)
    })
  })
})
