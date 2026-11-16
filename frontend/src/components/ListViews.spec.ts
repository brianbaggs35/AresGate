import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import * as viewsApi from '@/api/views'
import ListViews from '@/components/ListViews.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { kept } from '@/test/views'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function show(items: viewsApi.SavedView[] = [], route = '/incidents?view=all&severity=high') {
  vi.spyOn(viewsApi, 'fetchViews').mockResolvedValue(items)
  const mounted = await mountWithPlugins(ListViews, {
    signedIn: 'admin',
    route,
    props: { list: 'incidents' },
  })
  await flushPromises()
  const replace = vi.spyOn(mounted.router, 'replace')
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const all = (selector: string) => mounted.wrapper.findAll(`[data-test="${selector}"]`)
  const press = async (selector: string, index = 0) => {
    await all(selector)[index]?.trigger('click')
    await flushPromises()
  }
  return { ...mounted, replace, find, all, press }
}

const integration = (key: string, name: string, status: integrationsApi.Status) =>
  ({ key, name, status }) as integrationsApi.IntegrationSummary

describe('ListViews', () => {
  it('lists the views kept for its page, and says which is open now', async () => {
    const { all, find } = await show([
      kept({ id: 1, name: 'Needs a look' }),
      kept({ id: 2, name: 'Everything', query: {} }),
      kept({ id: 3, page: 'assets', name: 'Not here' }),
    ])

    expect(all('view-use').map((item) => item.text())).toEqual(['Needs a look', 'Everything'])
    expect(all('view-use')[0]?.attributes('aria-current')).toBe('true')
    expect(all('view-use')[1]?.attributes('aria-current')).toBeUndefined()
    expect(find('views-none').exists()).toBe(false)
  })

  it('says it is loading until they are here, and how to start when there are none', async () => {
    let arrive: (items: viewsApi.SavedView[]) => void = () => undefined
    vi.spyOn(viewsApi, 'fetchViews').mockReturnValue(
      new Promise((resolve) => {
        arrive = resolve
      }),
    )
    const { wrapper } = await mountWithPlugins(ListViews, {
      signedIn: 'admin',
      props: { list: 'incidents' },
    })

    expect(wrapper.text()).toContain('Loading…')

    arrive([])
    await flushPromises()

    expect(wrapper.text()).not.toContain('Loading…')
    expect(wrapper.find('[data-test="views-none"]').text()).toContain('Nothing is saved yet')
  })

  it('sets the page’s filters to a view when it is tapped', async () => {
    const { press, replace, find } = await show([kept({ query: { view: 'open', q: 'ssh' } })])

    await press('view-use')

    expect(replace).toHaveBeenCalledWith({ query: { view: 'open', q: 'ssh' } })
    expect(find('views-notice').text()).toBe('')
  })

  describe('a view that names a program', () => {
    it('opens anyway and says the program is not connected', async () => {
      vi.spyOn(integrationsApi, 'fetchIntegrations').mockResolvedValue([
        integration('wazuh', 'Wazuh', 'not_connected'),
        integration('opnsense', 'OPNsense', 'connected'),
      ])
      const { press, replace, find } = await show([
        kept({ query: { q: 'source:wazuh source:opnsense source:gone' } }),
      ])

      await press('view-use')

      expect(replace).toHaveBeenCalled()
      expect(find('views-notice').text()).toBe(
        'Needs a look is narrowed to Wazuh and gone, which are not connected any more. It opens anyway, and shows what is left.',
      )
    })

    it('says nothing for one that is connected', async () => {
      vi.spyOn(integrationsApi, 'fetchIntegrations').mockResolvedValue([
        integration('wazuh', 'Wazuh', 'connected'),
      ])
      const { press, find } = await show([kept({ query: { q: 'source:wazuh' } })])

      await press('view-use')

      expect(find('views-notice').text()).toBe('')
    })

    it('says "is" for just one', async () => {
      vi.spyOn(integrationsApi, 'fetchIntegrations').mockResolvedValue([
        integration('wazuh', 'Wazuh', 'not_connected'),
      ])
      const { press, find } = await show([kept({ query: { q: 'source:wazuh' } })])

      await press('view-use')

      expect(find('views-notice').text()).toContain('Wazuh, which is not connected any more')
    })

    it('says nothing when it cannot tell', async () => {
      vi.spyOn(integrationsApi, 'fetchIntegrations').mockRejectedValue(offline())
      const { press, find, replace } = await show([kept({ query: { source: 'wazuh' } })])

      await press('view-use')

      expect(replace).toHaveBeenCalled()
      expect(find('views-notice').text()).toBe('')
    })
  })

  describe('saving', () => {
    it('keeps what the page shows under a name', async () => {
      const save = vi
        .spyOn(viewsApi, 'saveView')
        .mockImplementation((page, name, query) =>
          Promise.resolve(kept({ id: 9, page, name, query })),
        )
      const { find, press } = await show()

      await find('view-name').find('input').setValue('  Highs  ')
      await press('view-save')

      expect(save).toHaveBeenCalledWith(
        'incidents',
        'Highs',
        { view: 'all', severity: 'high' },
        false,
        'a-security-token',
      )
      expect(find('views-notice').text()).toBe('Saved as Highs.')
      expect(find('view-use').text()).toBe('Highs')
      expect((find('view-name').find('input').element as HTMLInputElement).value).toBe('')
    })

    it('can make it the one the page opens on', async () => {
      const save = vi
        .spyOn(viewsApi, 'saveView')
        .mockImplementation((page, name, query) =>
          Promise.resolve(kept({ id: 9, page, name, query, is_default: true })),
        )
      const { find, press } = await show()

      await find('view-name').find('input').setValue('Highs')
      await find('view-as-default').find('input').setValue(true)
      await press('view-save')

      expect(save.mock.calls[0]?.[3]).toBe(true)
      expect(find('view-default').text()).toBe('Opens first')
    })

    it('says it replaces one when the name is taken, and cannot save without a name', async () => {
      const { find } = await show([kept({ name: 'Needs a look' })])

      expect(find('view-save').attributes('disabled')).toBeDefined()
      expect(find('view-save').text()).toBe('Save this view')

      await find('view-name').find('input').setValue('Needs a look')

      expect(find('view-save').text()).toBe('Replace')
    })

    it('says why it could not', async () => {
      vi.spyOn(viewsApi, 'saveView').mockRejectedValue(
        new ApiError(409, 'You can keep 20 views for this page.', 'conflict'),
      )
      const { find, press } = await show()

      await find('view-name').find('input').setValue('One more')
      await press('view-save')

      expect(find('views-failure').text()).toBe('You can keep 20 views for this page.')
      expect(find('views-notice').text()).toBe('')
    })
  })

  describe('renaming', () => {
    it('changes the name', async () => {
      const change = vi
        .spyOn(viewsApi, 'changeView')
        .mockResolvedValue(kept({ id: 1, name: 'Look at these' }))
      const { find, press } = await show([kept({ id: 1 })])

      await press('view-rename-start')
      await find('view-rename').find('input').setValue(' Look at these ')
      await find('view-rename-form').trigger('submit')
      await flushPromises()

      expect(change).toHaveBeenCalledWith(1, { name: 'Look at these' }, 'a-security-token')
      expect(find('views-notice').text()).toBe('Renamed to Look at these.')
      expect(find('view-use').text()).toBe('Look at these')
      expect(find('view-rename-form').exists()).toBe(false)
    })

    it('changes nothing when the name is the same or empty, and can be given up', async () => {
      const change = vi.spyOn(viewsApi, 'changeView')
      const { find, press } = await show([kept({ id: 1 })])

      await press('view-rename-start')
      await find('view-rename-form').trigger('submit')
      await flushPromises()

      expect(change).not.toHaveBeenCalled()
      expect(find('view-rename-form').exists()).toBe(false)

      await press('view-rename-start')
      await find('view-rename').find('input').setValue('  ')
      await find('view-rename-form').trigger('submit')
      await flushPromises()

      expect(change).not.toHaveBeenCalled()

      await press('view-rename-start')
      await press('view-rename-cancel')

      expect(find('view-rename-form').exists()).toBe(false)
    })

    it('stays open and says why when the name is taken', async () => {
      vi.spyOn(viewsApi, 'changeView').mockRejectedValue(
        new ApiError(409, 'You already have a view called Taken.', 'conflict'),
      )
      const { find, press } = await show([kept({ id: 1 })])

      await press('view-rename-start')
      await find('view-rename').find('input').setValue('Taken')
      await find('view-rename-form').trigger('submit')
      await flushPromises()

      expect(find('views-failure').text()).toBe('You already have a view called Taken.')
      expect(find('view-rename-form').exists()).toBe(true)
    })
  })

  describe('the one the page opens on', () => {
    it('is chosen with the star, and given up with it', async () => {
      const change = vi
        .spyOn(viewsApi, 'changeView')
        .mockResolvedValueOnce(kept({ id: 1, is_default: true }))
        .mockResolvedValueOnce(kept({ id: 1, is_default: false }))
      const { find, press } = await show([kept({ id: 1 })])

      expect(find('view-default-toggle').attributes('aria-pressed')).toBe('false')

      await press('view-default-toggle')

      expect(change).toHaveBeenLastCalledWith(1, { default: true }, 'a-security-token')
      expect(find('views-notice').text()).toBe('This page now opens on Needs a look.')
      expect(find('view-default-toggle').attributes('aria-pressed')).toBe('true')
      expect(find('view-default-toggle').attributes('aria-label')).toBe(
        'Stop opening on Needs a look',
      )

      await press('view-default-toggle')

      expect(change).toHaveBeenLastCalledWith(1, { default: false }, 'a-security-token')
      expect(find('views-notice').text()).toBe(
        'Needs a look is no longer the one this page opens on.',
      )
      expect(find('view-default').exists()).toBe(false)
    })
  })

  describe('forgetting', () => {
    it('forgets one', async () => {
      const forget = vi.spyOn(viewsApi, 'deleteView').mockResolvedValue(undefined)
      const { press, find, all } = await show([kept({ id: 1 }), kept({ id: 2, name: 'Other' })])

      await press('view-forget')

      expect(forget).toHaveBeenCalledWith(1, 'a-security-token')
      expect(all('view-use').map((item) => item.text())).toEqual(['Other'])
      expect(find('views-notice').text()).toBe('Forgot Needs a look.')
    })

    it('says why it could not', async () => {
      vi.spyOn(viewsApi, 'deleteView').mockRejectedValue(offline())
      const { press, find, all } = await show([kept({ id: 1 })])

      await press('view-forget')

      expect(find('views-failure').text()).toBe("Can't reach AresGate.")
      expect(all('view-use')).toHaveLength(1)
    })
  })

  it('says why the views could not be read', async () => {
    vi.spyOn(viewsApi, 'fetchViews').mockRejectedValue(offline())
    const { wrapper } = await mountWithPlugins(ListViews, {
      signedIn: 'admin',
      props: { list: 'incidents' },
    })
    await flushPromises()

    expect(wrapper.find('[data-test="views-failure"]').text()).toBe("Can't reach AresGate.")
    expect(wrapper.find('[data-test="views-none"]').exists()).toBe(false)
  })
})
