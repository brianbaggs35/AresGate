import * as auditApi from '@/api/audit'
import { settingsSections } from '@/settings'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import SettingsView from '@/views/SettingsView.vue'

async function open(route: string, width = 1280) {
  vi.spyOn(auditApi, 'fetchRecentActivity').mockResolvedValue([])
  const mounted = await mountWithPlugins(SettingsView, { route, width, signedIn: 'admin' })
  await vi.waitFor(() => {
    expect(mounted.router.currentRoute.value.matched.length).toBeGreaterThan(0)
  })
  await flushPromises()
  return mounted
}

describe('SettingsView', () => {
  it('has the one heading, and what the area is for', async () => {
    const { wrapper } = await open('/settings/activity')
    expect(wrapper.find('[data-test="page-heading"]').text()).toBe('Settings')
    expect(wrapper.find('[data-test="page-description"]').text()).toContain('Your account')
  })

  it('lists every settings page, and shows the one that is open beside the list', async () => {
    const { wrapper } = await open('/settings/activity')
    for (const section of settingsSections)
      expect(wrapper.find(`[data-test="settings-nav-${section.key}"]`).exists()).toBe(true)
    expect(wrapper.find('[data-test="activity-card"]').exists()).toBe(true)
  })

  it('shows the page that is chosen in the list', async () => {
    const { wrapper, router } = await open('/settings/activity')
    await router.push({ name: 'settings-account' })
    await vi.waitFor(() => {
      expect(wrapper.find('[data-test="activity-card"]').exists()).toBe(false)
    })
  })

  it('has tabs instead of the list on a phone', async () => {
    const { wrapper } = await open('/settings/activity', 500)
    expect(wrapper.find('.v-tabs').exists()).toBe(true)
  })
})
