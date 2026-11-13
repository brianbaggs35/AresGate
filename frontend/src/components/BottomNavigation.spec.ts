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
    const dashboard = wrapper.find('[data-test="nav-home"]')
    expect(dashboard.text()).toBe('Dashboard')
    expect(dashboard.attributes('href')).toBe('/')
    expect(dashboard.classes()).toContain('v-btn--active')
  })

  it('keeps More marked on the page of one of a conversation, which is behind it', async () => {
    const { wrapper } = await open('/assistant/5')
    expect(wrapper.find('[data-test="nav-more"]').classes()).toContain('v-btn--active')
    expect(wrapper.find('[data-test="nav-home"]').classes()).not.toContain('v-btn--active')
  })

  it('marks Review when it is open', async () => {
    const { wrapper } = await open('/review')
    expect(wrapper.find('[data-test="nav-review"]').classes()).toContain('v-btn--active')
  })

  it('keeps Incidents marked on the page of one of them', async () => {
    const { wrapper } = await open('/incidents/7')
    expect(wrapper.find('[data-test="nav-incidents"]').classes()).toContain('v-btn--active')
    expect(wrapper.find('[data-test="nav-home"]').classes()).not.toContain('v-btn--active')
  })

  it('marks nothing on a page that is not in the menu', async () => {
    const { wrapper } = await open('/no/such/page')
    expect(wrapper.find('[data-test="nav-home"]').classes()).not.toContain('v-btn--active')
  })

  it('holds the places that fit, and More for the rest', async () => {
    const { wrapper } = await open('/')

    expect(
      wrapper.findAll('.v-bottom-navigation .v-btn').map((place) => place.attributes('data-test')),
    ).toEqual(['nav-home', 'nav-threats', 'nav-incidents', 'nav-review', 'nav-more'])
    expect(wrapper.find('[data-test="nav-more"]').text()).toBe('More')
    expect(wrapper.find('[data-test="nav-status"]').exists()).toBe(false)
  })

  it('has no More button while every place fits', async () => {
    const { wrapper } = await mountWithPlugins(BottomNavigation, {
      withApp: true,
      width: 400,
      route: '/',
      props: {
        items: [
          { route: 'home', title: 'Dashboard', icon: 'x' },
          { route: 'logs', title: 'Logs', icon: 'x' },
        ],
      },
    })

    expect(wrapper.find('[data-test="nav-more"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="nav-logs"]').exists()).toBe(true)
  })

  describe('More', () => {
    const inSheet = (selector: string) =>
      document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

    it('opens the other places in a sheet, and says that it has', async () => {
      const { wrapper } = await open('/')
      const more = wrapper.find('[data-test="nav-more"]')
      expect(more.attributes('aria-expanded')).toBe('false')
      expect(more.attributes('aria-haspopup')).toBe('dialog')
      expect(inSheet('more-sheet')).toBeNull()

      await more.trigger('click')
      await flushPromises()

      expect(more.attributes('aria-expanded')).toBe('true')
      expect(
        [...(inSheet('more-sheet')?.querySelectorAll('a') ?? [])].map((place) =>
          place.textContent.trim(),
        ),
      ).toEqual([
        'Assistant',
        'Agents',
        'Logs',
        'Assets',
        'Devices',
        'Integrations',
        'Threat intelligence',
        'Interfaces',
        'AI usage',
        'Trust',
        'Alerts',
        'Status',
        'Settings',
      ])
      expect(inSheet('nav-status')?.getAttribute('href')).toBe('/status')
    })

    it('puts the sheet away when Escape is pressed', async () => {
      const { wrapper } = await open('/')
      const more = wrapper.find('[data-test="nav-more"]')
      await more.trigger('click')
      await flushPromises()
      expect(more.attributes('aria-expanded')).toBe('true')

      inSheet('more-sheet')?.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
      )
      await flushPromises()

      expect(more.attributes('aria-expanded')).toBe('false')
    })

    it('goes to a place when it is tapped, and puts the sheet away', async () => {
      const { wrapper, router } = await open('/')
      await wrapper.find('[data-test="nav-more"]').trigger('click')
      await flushPromises()

      inSheet('nav-settings')?.click()

      // The pages of Settings are loaded when they are first asked for, which takes a moment.
      await vi.waitFor(
        () => {
          expect(router.currentRoute.value.name).toBe('settings-account')
        },
        {
          timeout: 4000,
        },
      )
      expect(wrapper.find('[data-test="nav-more"]').attributes('aria-expanded')).toBe('false')
    })

    it.each(['/logs', '/ai-usage', '/trust', '/status', '/settings/account', '/settings/activity'])(
      'is marked as the place that is open on %s',
      async (route) => {
        const { wrapper } = await open(route)
        const more = wrapper.find('[data-test="nav-more"]')

        expect(more.classes()).toContain('v-btn--active')
        expect(more.attributes('aria-current')).toBe('true')
      },
    )

    it.each(['/', '/threats/kinds/3', '/incidents/7', '/no/such/page'])(
      'is not marked on %s',
      async (route) => {
        const { wrapper } = await open(route)
        const more = wrapper.find('[data-test="nav-more"]')

        expect(more.classes()).not.toContain('v-btn--active')
        expect(more.attributes('aria-current')).toBeUndefined()
      },
    )
  })

  it('keeps Threats marked on the page of a kind of incident', async () => {
    const { wrapper } = await open('/threats/kinds/3')

    expect(wrapper.find('[data-test="nav-threats"]').classes()).toContain('v-btn--active')
  })

  it('goes to a place when it is tapped', async () => {
    const { wrapper, router } = await open('/no/such/page')
    await wrapper.find('[data-test="nav-home"]').trigger('click')
    await vi.waitFor(
      () => {
        expect(router.currentRoute.value.name).toBe('home')
      },
      { timeout: 4000 },
    )
  })
})
