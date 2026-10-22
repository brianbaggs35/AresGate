import BottomNavigation from '@/components/BottomNavigation.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const open = (route: string) =>
  mountWithPlugins(BottomNavigation, { withApp: true, width: 400, route })

describe('BottomNavigation', () => {
  it('names the menu', async () => {
    const { wrapper } = await open('/')
    expect(wrapper.find('nav').attributes('aria-label')).toBe('Main')
  })

  it('lists the places, and marks the one that is open', async () => {
    const { wrapper } = await open('/')
    const overview = wrapper.find('[data-test="nav-home"]')
    expect(overview.text()).toBe('Overview')
    expect(overview.attributes('href')).toBe('/')
    expect(overview.classes()).toContain('v-btn--active')
  })

  it('marks nothing on a page that is not in the menu', async () => {
    const { wrapper } = await open('/no/such/page')
    expect(wrapper.find('[data-test="nav-home"]').classes()).not.toContain('v-btn--active')
  })

  it('goes to a place when it is tapped', async () => {
    const { wrapper, router } = await open('/no/such/page')
    await wrapper.find('[data-test="nav-home"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('home')
  })
})
