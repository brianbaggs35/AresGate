import AppBar from '@/components/AppBar.vue'
import { usePaletteStore } from '@/stores/palette'
import { mountWithPlugins } from '@/test/mount'

const open = (width: number, route: string) =>
  mountWithPlugins(AppBar, { withApp: true, width, route })

describe('AppBar', () => {
  it("shows the page's title beside the menu", async () => {
    const { wrapper } = await open(1280, '/')
    expect(wrapper.find('[data-test="page-title"]').text()).toBe('Dashboard')
    expect(wrapper.find('[data-test="app-logo"]').exists()).toBe(false)
  })

  it('has no title for a page that gives none', async () => {
    const { wrapper, router } = await open(1280, '/')
    router.addRoute({ path: '/untitled', component: { render: () => null } })
    await router.push('/untitled')
    expect(wrapper.find('[data-test="page-title"]').text()).toBe('')
  })

  it('shows the logo on a phone, whose menu is at the bottom, and links it home', async () => {
    const { wrapper } = await open(400, '/no/such/page')
    expect(wrapper.find('[data-test="page-title"]').exists()).toBe(false)
    expect(wrapper.find('a[aria-label="AresGate"]').attributes('href')).toBe('/')
  })

  it('has a search button that opens the palette, and tells the keys that do too', async () => {
    const { wrapper } = await open(1280, '/')
    const button = wrapper.find('[data-test="palette-open"]')
    expect(button.text()).toContain('Search')
    expect(button.find('kbd').text()).toBe('Ctrl K')
    expect(button.attributes('aria-keyshortcuts')).toBe('Control+K Meta+K')

    await button.trigger('click')
    expect(usePaletteStore().open).toBe(true)
    await button.trigger('click')
    expect(usePaletteStore().open).toBe(false)
  })

  it('has just an icon for it on a phone, which has no such keys', async () => {
    const { wrapper } = await open(400, '/')
    const button = wrapper.find('[data-test="palette-open"]')
    expect(button.attributes('aria-label')).toBe('Search')
    expect(button.text()).toBe('')
    expect(button.find('kbd').exists()).toBe(false)

    await button.trigger('click')
    expect(usePaletteStore().open).toBe(true)
  })

  it('has the theme switcher', async () => {
    const { wrapper } = await open(1280, '/')
    expect(wrapper.find('[data-test="theme-toggle"]').exists()).toBe(true)
  })
})
