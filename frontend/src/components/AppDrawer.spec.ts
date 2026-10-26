import { VTooltip } from 'vuetify/components'

import AppDrawer from '@/components/AppDrawer.vue'
import { MENU_STORAGE_KEY } from '@/stores/navigation'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const COMPUTER = 1280
const TABLET = 700

const open = (width: number) => mountWithPlugins(AppDrawer, { withApp: true, width, route: '/' })
const toggle = (wrapper: Awaited<ReturnType<typeof open>>['wrapper']) =>
  wrapper.find('[data-test="menu-width"]')

describe('AppDrawer', () => {
  it('names the menu, and the logo links home', async () => {
    const { wrapper } = await open(COMPUTER)
    expect(wrapper.find('nav').attributes('aria-label')).toBe('Main')
    const logo = wrapper.find('a[aria-label="AresGate"]')
    expect(logo.attributes('href')).toBe('/')
    expect(logo.text()).toBe('AresGate')
  })

  it('lists the places, and marks the one that is open', async () => {
    const { wrapper } = await open(COMPUTER)
    const dashboard = wrapper.find('[data-test="nav-home"]')
    expect(dashboard.text()).toBe('Dashboard')
    expect(dashboard.attributes('href')).toBe('/')
    expect(dashboard.classes()).toContain('v-list-item--active')
  })

  it('keeps Integrations marked on the page of one of them', async () => {
    const { wrapper } = await mountWithPlugins(AppDrawer, {
      withApp: true,
      width: COMPUTER,
      route: '/integrations/opnsense',
    })
    expect(wrapper.find('[data-test="nav-integrations"]').classes()).toContain(
      'v-list-item--active',
    )
    expect(wrapper.find('[data-test="nav-home"]').classes()).not.toContain('v-list-item--active')
  })

  it('shows the labels on a computer', async () => {
    const { wrapper } = await open(COMPUTER)
    expect(wrapper.find('.v-navigation-drawer--rail').exists()).toBe(false)
    expect(toggle(wrapper).attributes('aria-label')).toBe('Collapse the menu')
    expect(toggle(wrapper).attributes('aria-expanded')).toBe('true')
    expect(wrapper.findComponent(VTooltip).exists()).toBe(false)
  })

  it("starts as a rail on a tablet, with the logo's mark alone and tooltips for the places", async () => {
    const { wrapper } = await open(TABLET)
    expect(wrapper.find('.v-navigation-drawer--rail').exists()).toBe(true)
    expect(wrapper.find('a[aria-label="AresGate"]').text()).toBe('')
    expect(toggle(wrapper).attributes('aria-label')).toBe('Expand the menu')
    expect(toggle(wrapper).attributes('aria-expanded')).toBe('false')
    expect(wrapper.findComponent(VTooltip).props('text')).toBe('Dashboard')
  })

  it('collapses to a rail, and remembers it', async () => {
    const { wrapper } = await open(COMPUTER)
    await toggle(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.find('.v-navigation-drawer--rail').exists()).toBe(true)
    expect(localStorage.getItem(MENU_STORAGE_KEY)).toBe('rail')
  })

  it('expands from a rail, and remembers it', async () => {
    const { wrapper } = await open(TABLET)
    await toggle(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.find('.v-navigation-drawer--rail').exists()).toBe(false)
    expect(localStorage.getItem(MENU_STORAGE_KEY)).toBe('full')
  })

  it('follows a saved choice over the size of the screen', async () => {
    const { wrapper } = await mountWithPlugins(AppDrawer, {
      withApp: true,
      width: TABLET,
      route: '/',
      beforeMount: () => {
        localStorage.setItem(MENU_STORAGE_KEY, 'full')
      },
    })
    expect(wrapper.find('.v-navigation-drawer--rail').exists()).toBe(false)
  })
})
