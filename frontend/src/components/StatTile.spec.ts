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

  describe('how it has changed', () => {
    it.each([
      ['up', 'good', 'text-success'],
      ['down', 'bad', 'text-error'],
    ] as const)(
      'says %s, as good or bad, in words, with an arrow',
      async (direction, tone, color) => {
        const { wrapper } = await mountWithPlugins(StatTile, {
          props: {
            label: 'Blocked',
            value: 40,
            delta: { text: '+12% since yesterday', direction, tone },
          },
        })

        const delta = wrapper.find('[data-test="stat-delta"]')
        expect(delta.text()).toBe('+12% since yesterday')
        expect(delta.classes()).toContain(color)
        expect(delta.find('.v-icon').attributes('aria-hidden')).toBe('true')
      },
    )

    it('says no change in no color', async () => {
      const { wrapper } = await mountWithPlugins(StatTile, {
        props: {
          label: 'Blocked',
          value: 40,
          delta: { text: 'No change', direction: 'flat', tone: 'neutral' },
        },
      })

      const delta = wrapper.find('[data-test="stat-delta"]')
      expect(delta.classes()).not.toContain('text-success')
      expect(delta.classes()).not.toContain('text-error')
    })

    it('has no line for a change it was not told of', async () => {
      const { wrapper } = await mountWithPlugins(StatTile, {
        props: { label: 'Blocked', value: 40 },
      })

      expect(wrapper.find('[data-test="stat-delta"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="sparkline"]').exists()).toBe(false)
    })
  })

  describe('how it has been going', () => {
    it('draws a small line beside the number, described in words, in the tile’s own color', async () => {
      const { wrapper } = await mountWithPlugins(StatTile, {
        props: {
          label: 'Blocked',
          value: 40,
          tone: 'bad',
          trend: [1, 5, 3, 8],
          trendLabel: 'Blocked per hour, now 8',
        },
      })

      expect(wrapper.find('[data-test="sparkline"]').exists()).toBe(true)
      expect(wrapper.find('[role="img"]').attributes('aria-label')).toBe('Blocked per hour, now 8')
      expect(wrapper.find('[data-test="sparkline-dot"]').attributes('style')).toContain(
        'rgb(var(--v-theme-error))',
      )
    })

    it('has a name for the line even when it was not given one', async () => {
      const { wrapper } = await mountWithPlugins(StatTile, {
        props: { label: 'Blocked', value: 40, trend: [1, 2] },
      })

      expect(wrapper.find('[role="img"]').attributes('aria-label')).toBe('Trend')
      expect(wrapper.find('[data-test="sparkline-dot"]').attributes('style')).toContain(
        'rgb(var(--v-theme-primary))',
      )
    })

    it('leaves the line out when there is no trend yet', async () => {
      const { wrapper } = await mountWithPlugins(StatTile, {
        props: { label: 'Blocked', value: 40, trend: [] },
      })

      expect(wrapper.find('[role="img"]').exists()).toBe(false)
    })
  })
})
