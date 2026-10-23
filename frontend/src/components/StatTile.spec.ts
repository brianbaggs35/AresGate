import { Activity } from '@lucide/vue'

import StatTile from '@/components/StatTile.vue'
import { mountWithPlugins } from '@/test/mount'

describe('StatTile', () => {
  it('shows a number with its name and what it is measured against', async () => {
    const { wrapper } = await mountWithPlugins(StatTile, {
      props: { label: 'Blocked', value: 1284, hint: 'Last 24 hours', icon: Activity },
    })
    expect(wrapper.find('[data-test="stat-label"]').text()).toBe('Blocked')
    expect(wrapper.find('[data-test="stat-value"]').text()).toBe('1284')
    expect(wrapper.find('[data-test="stat-hint"]').text()).toBe('Last 24 hours')
    expect(wrapper.find('.v-icon').attributes('aria-hidden')).toBe('true')
  })

  it('can be just a name and a value', async () => {
    const { wrapper } = await mountWithPlugins(StatTile, {
      props: { label: 'Uptime', value: '9d' },
    })
    expect(wrapper.find('[data-test="stat-hint"]').exists()).toBe(false)
    expect(wrapper.find('.v-icon').exists()).toBe(false)
    expect(wrapper.find('a').exists()).toBe(false)
  })

  it.each([
    ['neutral', 'text-primary'],
    ['good', 'text-success'],
    ['warning', 'text-warning'],
    ['bad', 'text-error'],
  ] as const)('colors the icon of a %s tile', async (tone, color) => {
    const { wrapper } = await mountWithPlugins(StatTile, {
      props: { label: 'Gateway', value: 'Up', icon: Activity, tone },
    })
    expect(wrapper.find('.v-icon').classes()).toContain(color)
  })

  it('leads to where the number comes from', async () => {
    const { wrapper, router } = await mountWithPlugins(StatTile, {
      props: { label: 'Integrations', value: 4, to: { name: 'integrations' } },
    })
    expect(wrapper.find('a').attributes('href')).toBe('/integrations')
    await wrapper.find('a').trigger('click')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('integrations')
    })
  })
})
