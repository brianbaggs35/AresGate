import SettingsNav from '@/components/SettingsNav.vue'
import { settingsSections } from '@/settings'
import { mountWithPlugins } from '@/test/mount'

const KEYS = settingsSections.map((section) => section.key)

async function show(width: number, route = '/settings/account') {
  return mountWithPlugins(SettingsNav, { route, width, props: { sections: settingsSections } })
}

describe('SettingsNav', () => {
  it('is a navigation landmark called Settings', async () => {
    const { wrapper } = await show(1280)
    expect(wrapper.find('nav').attributes('aria-label')).toBe('Settings')
  })

  it('lists every page as a link beside the page on a computer', async () => {
    const { wrapper } = await show(1280)
    expect(wrapper.find('.v-tabs').exists()).toBe(false)
    const links = KEYS.map((key) => wrapper.find(`[data-test="settings-nav-${key}"]`))
    expect(links.map((link) => link.attributes('href'))).toEqual([
      '/settings/account',
      '/settings/sign-ins',
      '/settings/activity',
      '/settings/verdicts',
      '/settings/ai',
      '/settings/data',
    ])
    expect(links.map((link) => link.text())).toEqual([
      'Account',
      'Sign-ins',
      'Activity',
      'Verdicts',
      'AI',
      'Data',
    ])
  })

  it('marks the page that is open', async () => {
    const { wrapper } = await show(1280, '/settings/sign-ins')
    expect(wrapper.find('[data-test="settings-nav-sign-ins"]').classes()).toContain(
      'v-list-item--active',
    )
    expect(wrapper.find('[data-test="settings-nav-account"]').classes()).not.toContain(
      'v-list-item--active',
    )
  })

  it('is tabs above the page on a phone, with the same links', async () => {
    const { wrapper } = await show(500, '/settings/activity')
    expect(wrapper.find('.v-list').exists()).toBe(false)
    expect(wrapper.find('.v-tabs').exists()).toBe(true)
    const tabs = wrapper.findAll('.v-tab')
    expect(tabs.map((tab) => tab.attributes('href'))).toEqual([
      '/settings/account',
      '/settings/sign-ins',
      '/settings/activity',
      '/settings/verdicts',
      '/settings/ai',
      '/settings/data',
    ])
    expect(tabs.map((tab) => tab.text())).toEqual([
      'Account',
      'Sign-ins',
      'Activity',
      'Verdicts',
      'AI',
      'Data',
    ])
    expect(tabs[2]?.classes()).toContain('v-tab--selected')
  })
})
