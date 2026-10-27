import { ApiError } from '@/api/client'
import * as searchesApi from '@/api/searches'
import SavedSearches from '@/components/SavedSearches.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { saved } from '@/test/searches'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function show(
  kept: searchesApi.SavedSearch[] = [],
  props: Partial<InstanceType<typeof SavedSearches>['$props']> = {},
) {
  const fetch = vi.spyOn(searchesApi, 'fetchSavedSearches').mockResolvedValue(kept)
  const save = vi
    .spyOn(searchesApi, 'saveSearch')
    .mockImplementation((scope, name, query) =>
      Promise.resolve(saved({ id: 9, scope, name, query })),
    )
  const forget = vi.spyOn(searchesApi, 'deleteSavedSearch').mockResolvedValue(undefined)
  const mounted = await mountWithPlugins(SavedSearches, {
    signedIn: 'admin',
    props: { scope: 'logs', current: 'kind:alert', savable: true, ...props },
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const names = () => mounted.wrapper.findAll('[data-test="saved-use"] span').map((n) => n.text())
  const name = (text: string) => find('saved-name').find('input').setValue(text)
  const press = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  return { ...mounted, fetch, save, forget, find, names, name, press }
}

describe('SavedSearches', () => {
  it('lists what is kept for its page, each with its words', async () => {
    const { fetch, wrapper, names } = await show([
      saved({ id: 1, name: 'Scans', query: 'kind:alert since:6h' }),
      saved({ id: 2, name: 'SSH', query: 'port:22' }),
    ])

    expect(fetch).toHaveBeenCalledWith('logs')
    expect(names()).toEqual(['Scans', 'SSH'])
    expect(wrapper.findAll('[data-test="saved-use"] code').map((c) => c.text())).toEqual([
      'kind:alert since:6h',
      'port:22',
    ])
    expect(wrapper.find('section').attributes('aria-labelledby')).toBeTruthy()
  })

  it('says it is loading until they are here', async () => {
    let arrive: (items: searchesApi.SavedSearch[]) => void = () => undefined
    vi.spyOn(searchesApi, 'fetchSavedSearches').mockReturnValue(
      new Promise((resolve) => {
        arrive = resolve
      }),
    )
    const { wrapper } = await mountWithPlugins(SavedSearches, {
      signedIn: 'admin',
      props: { scope: 'incidents', current: '', savable: false },
    })

    expect(wrapper.find('[data-test="saved-loading"]').text()).toBe('Loading…')

    arrive([])
    await flushPromises()

    expect(wrapper.find('[data-test="saved-loading"]').exists()).toBe(false)
  })

  it('says how to start when there is nothing', async () => {
    const { find } = await show([])

    expect(find('saved-none').text()).toContain('Nothing is saved yet')
  })

  it('hands a search to the box when it is tapped', async () => {
    const { wrapper, press } = await show([saved({ query: 'kind:alert since:6h' })])

    await press('saved-use')

    expect(wrapper.emitted('use')).toEqual([['kind:alert since:6h']])
  })

  it('says so when they cannot be read, and offers no empty list', async () => {
    vi.spyOn(searchesApi, 'fetchSavedSearches').mockRejectedValue(offline())
    const { wrapper } = await mountWithPlugins(SavedSearches, {
      signedIn: 'admin',
      props: { scope: 'logs', current: '', savable: false },
    })
    await flushPromises()

    expect(wrapper.find('[data-test="saved-failure"]').text()).toBe("Can't reach AresGate.")
    expect(wrapper.find('[data-test="saved-failure"]').attributes('role')).toBe('alert')
    expect(wrapper.find('[data-test="saved-none"]').exists()).toBe(false)
  })

  describe('keeping the search in the box', () => {
    it('has no way to name it while there is nothing to keep', async () => {
      const { find } = await show([], { savable: false })

      expect(find('saved-form').exists()).toBe(false)
    })

    it('cannot be saved before it has a name', async () => {
      const { find, name } = await show()

      expect(find('saved-save').attributes('disabled')).toBeDefined()

      await name('   ')
      expect(find('saved-save').attributes('disabled')).toBeDefined()

      await name('Scans')
      expect(find('saved-save').attributes('disabled')).toBeUndefined()
    })

    it('keeps what is in the box under the name, and says so', async () => {
      const { save, find, names, name, press } = await show([saved({ id: 1, name: 'SSH' })])

      await name('  Scans ')
      expect(find('saved-save').text()).toBe('Save')
      await press('saved-save')

      expect(save).toHaveBeenCalledWith('logs', 'Scans', 'kind:alert', expect.any(String))
      expect(names()).toEqual(['Scans', 'SSH'])
      expect(find('saved-notice').text()).toBe('Saved as Scans.')
      expect(find('saved-name').find<HTMLInputElement>('input').element.value).toBe('')
    })

    it('says it replaces one when the name is taken', async () => {
      const { save, find, wrapper, names, name, press } = await show([
        saved({ id: 1, name: 'Scans', query: 'port:22' }),
      ])
      // The API answers with the one that was there, changed.
      save.mockResolvedValue(saved({ id: 1, name: 'Scans', query: 'kind:alert' }))

      await name('Scans')
      expect(find('saved-save').text()).toBe('Replace')
      await press('saved-save')

      expect(names()).toEqual(['Scans'])
      expect(wrapper.find('[data-test="saved-use"] code').text()).toBe('kind:alert')
      expect(find('saved-notice').text()).toBe('Saved as Scans.')
    })

    it('keeps them by name, whatever the case', async () => {
      const { names, name, press } = await show([
        saved({ id: 1, name: 'alpha' }),
        saved({ id: 2, name: 'Gamma' }),
      ])

      await name('beta')
      await press('saved-save')

      expect(names()).toEqual(['alpha', 'beta', 'Gamma'])
    })

    it('puts two with the same name by when they were made, as the API does', async () => {
      const { names, name, press } = await show([saved({ id: 5, name: 'Same' })])
      vi.spyOn(searchesApi, 'saveSearch').mockResolvedValue(saved({ id: 3, name: 'same' }))

      await name('same')
      await press('saved-save')

      expect(names()).toEqual(['same', 'Same'])
    })

    it('says why when it could not be kept', async () => {
      const { save, find, names, name, press } = await show()
      save.mockRejectedValue(new ApiError(409, 'You can keep 50 searches for this page.', 'x'))

      await name('Scans')
      await press('saved-save')

      expect(find('saved-failure').text()).toBe('You can keep 50 searches for this page.')
      expect(find('saved-notice').text()).toBe('')
      expect(names()).toEqual([])
      expect(find('saved-name').find<HTMLInputElement>('input').element.value).toBe('Scans')
    })
  })

  describe('forgetting one', () => {
    it('takes it off the list and says so', async () => {
      const { forget, find, names, press } = await show([
        saved({ id: 1, name: 'Scans' }),
        saved({ id: 2, name: 'SSH' }),
      ])
      expect(find('saved-forget').attributes('aria-label')).toBe('Forget Scans')

      await press('saved-forget')

      expect(forget).toHaveBeenCalledWith(1, expect.any(String))
      expect(names()).toEqual(['SSH'])
      expect(find('saved-notice').text()).toBe('Forgot Scans.')
    })

    it('says why when it could not, and keeps it', async () => {
      const { forget, find, names, press } = await show([saved()])
      forget.mockRejectedValue(offline())

      await press('saved-forget')

      expect(find('saved-failure').text()).toBe("Can't reach AresGate.")
      expect(names()).toEqual(['Scans'])
    })
  })
})
