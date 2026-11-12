import { VBtnToggle, VSelect } from 'vuetify/components'

import * as assetsApi from '@/api/assets'
import { ApiError } from '@/api/client'
import AssetCard from '@/components/AssetCard.vue'
import AssetSearch from '@/components/AssetSearch.vue'
import AssetSuppliers from '@/components/AssetSuppliers.vue'
import { asset, counts, machine, page, supplier } from '@/test/assets'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AssetsView from '@/views/AssetsView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

/** Three assets: a laptop that is on, a phone that was seen today and a camera that was not. */
function some() {
  return page(
    [
      asset({ key: 'device-1', name: 'Laptop', interfaces: [4] }),
      asset({ key: 'device-2', name: 'Phone', status: 'recent', is_new: true }),
      asset({ key: 'device-3', name: 'Camera', status: 'away', identified: false }),
    ],
    {
      counts: counts({ all: 3, online: 1, recent: 1, away: 1 }),
      suppliers: [
        supplier({ assets: 3 }),
        supplier({ key: 'ntopng', name: 'ntopng', ways: ['Active hosts'], assets: 2 }),
        supplier({ key: 'wazuh', name: 'Wazuh', ways: ['Agent'], connected: false, assets: 0 }),
      ],
      interfaces: [
        { id: 4, name: 'Home', assets: 2 },
        { id: 5, name: 'IoT', assets: 1 },
      ],
      new: 1,
      unidentified: 1,
    },
  )
}

interface Options {
  route?: string
  answer?: assetsApi.AssetPage | Error
}

async function open({ route = '/assets', answer = some() }: Options = {}) {
  const fetchAssets = vi.spyOn(assetsApi, 'fetchAssets')
  if (answer instanceof Error) fetchAssets.mockRejectedValue(answer)
  else fetchAssets.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(AssetsView, { signedIn: 'admin', withApp: true, route })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const names = () => mounted.wrapper.findAll('[data-test="asset-name"]').map((name) => name.text())
  /** Does what someone does to the filters, and waits for the new address of the page (which
   * takes a moment to arrive) and for the list to be asked for again. */
  const choose = async (act: () => unknown) => {
    await act()
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, fetchAssets, find, text, names, choose }
}

function last(fetchAssets: { mock: { calls: unknown[][] } }) {
  return fetchAssets.mock.calls.at(-1)?.[0] as assetsApi.AssetQuery
}

describe('AssetsView', () => {
  it('asks for the first page, with every state and no choices', async () => {
    const { fetchAssets } = await open()

    expect(fetchAssets).toHaveBeenCalledTimes(1)
    expect(last(fetchAssets)).toEqual({
      sources: [],
      new: false,
      unidentified: false,
      sort: 'recent',
      limit: 30,
      offset: 0,
    })
  })

  it('shows a skeleton until the first answer arrives', async () => {
    vi.spyOn(assetsApi, 'fetchAssets').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(AssetsView, { signedIn: 'admin' })

    expect(wrapper.find('[data-test="assets-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="asset-list"]').exists()).toBe(false)
  })

  it('has a heading and says how many there are and how many are on', async () => {
    const { wrapper, text } = await open()

    expect(wrapper.find('h1').text()).toBe('Assets')
    expect(wrapper.find('[data-test="page-description"]').text()).toBe('3 assets, 1 online now.')
    expect(text('asset-list')).not.toBe('')
  })

  it('says "1 asset" for one', async () => {
    const { wrapper } = await open({ answer: page([asset()]) })

    expect(wrapper.find('[data-test="page-description"]').text()).toBe('1 asset, 1 online now.')
  })

  it('lists them as they were sent, each on a card that names the interfaces it is on', async () => {
    const { names, wrapper } = await open()

    expect(names()).toEqual(['Laptop', 'Phone', 'Camera'])
    const cards = wrapper.findAllComponents(AssetCard)
    expect(cards.map((card) => card.props('interfaces'))).toEqual([['Home'], [], []])
  })

  it('leaves out an interface it was not told the name of', async () => {
    const { wrapper } = await open({
      answer: page([asset({ interfaces: [4, 99] })], {
        interfaces: [{ id: 4, name: 'Home', assets: 1 }],
      }),
    })

    expect(wrapper.findComponent(AssetCard).props('interfaces')).toEqual(['Home'])
  })

  it('has a heading for the list so the page can be read by its headings', async () => {
    const { wrapper } = await open()

    expect(wrapper.findAll('h2').map((heading) => heading.text())).toEqual([
      'Assets',
      'Where the assets come from',
    ])
  })

  it('says where the assets come from', async () => {
    const { wrapper } = await open()

    expect(wrapper.findComponent(AssetSuppliers).props('suppliers')).toHaveLength(3)
  })

  it('explains what new means, and when it began to watch', async () => {
    const { text } = await open()

    expect(text('assets-note')).toContain('New means first listed in the last 7 days')
  })

  it('says nothing of when it began to watch while there is nothing to watch', async () => {
    const { find } = await open({ answer: page([], { watching_since: null }) })

    expect(find('assets-note').exists()).toBe(false)
  })

  it('says what is left out for being on the Internet side, and that the firewall stays', async () => {
    const { text } = await open({ answer: { ...some(), outside: 2 } })

    expect(text('assets-outside')).toContain(
      "2 devices on the Internet side are not listed, such as your provider's equipment.",
    )
    expect(text('assets-outside')).toContain("Your firewall's own addresses stay listed.")
  })

  it('says one device for one left out on the Internet side', async () => {
    const { text } = await open({ answer: { ...some(), outside: 1 } })

    expect(text('assets-outside')).toContain(
      "1 device on the Internet side is not listed, such as your provider's equipment.",
    )
  })

  it('says nothing of the Internet side when nothing is left out', async () => {
    const { find } = await open({ answer: some() })

    expect(find('assets-outside').exists()).toBe(false)
  })

  it('says when the numbers on screen arrived', async () => {
    const { text } = await open()

    expect(text('updated')).toMatch(/^Updated \d/)
    expect(text('updated')).toContain('every 30 seconds')
  })

  describe('when it cannot load', () => {
    it('says why, and tries again', async () => {
      const { find, fetchAssets, choose } = await open({ answer: offline() })

      expect(find('assets-error').text()).toContain("Can't reach AresGate.")
      expect(find('asset-list').exists()).toBe(false)
      fetchAssets.mockResolvedValue(some())

      await choose(() => find('retry').trigger('click'))

      expect(find('assets-error').exists()).toBe(false)
      expect(find('asset-list').exists()).toBe(true)
    })

    it('keeps what it has on screen when a later look fails, and says so', async () => {
      const { find, fetchAssets, choose } = await open()
      fetchAssets.mockRejectedValue(offline())

      await choose(() => find('refresh').trigger('click'))

      expect(find('assets-stale').text()).toContain("Can't reach AresGate.")
      expect(find('assets-stale').text()).toContain('What is shown is from')
      expect(find('asset-list').exists()).toBe(true)
      fetchAssets.mockResolvedValue(some())

      await choose(() => find('refresh').trigger('click'))

      expect(find('assets-stale').exists()).toBe(false)
    })
  })

  describe('the states', () => {
    it('start from all of them, with nothing in the address of the page', async () => {
      const { find, router } = await open()

      expect(find('view-all').classes()).toContain('v-btn--active')
      expect(find('view-all').attributes('aria-pressed')).toBe('true')
      expect(find('view-away').attributes('aria-pressed')).toBe('false')
      expect(router.currentRoute.value.query).toEqual({})
    })

    it('count the assets in each, from every one there is', async () => {
      const { text } = await open()

      expect(text('count-all')).toBe('3')
      expect(text('count-online')).toBe('1')
      expect(text('count-recent')).toBe('1')
      expect(text('count-away')).toBe('1')
    })

    it('ask for one, and say so in the address, so a link brings it back', async () => {
      const { find, router, fetchAssets, choose } = await open()

      await choose(() => find('view-recent').trigger('click'))

      expect(last(fetchAssets).status).toBe('recent')
      expect(router.currentRoute.value.query).toEqual({ status: 'recent' })
      expect(find('view-recent').classes()).toContain('v-btn--active')
    })

    it('ask for all of them again with no state', async () => {
      const { find, router, fetchAssets, choose } = await open({ route: '/assets?status=away' })
      expect(last(fetchAssets).status).toBe('away')

      await choose(() => find('view-all').trigger('click'))

      expect(last(fetchAssets).status).toBeUndefined()
      expect(router.currentRoute.value.query).toEqual({})
    })

    it('stay as they are when the choice is taken away, which a state cannot be', async () => {
      const { wrapper, fetchAssets, choose, find } = await open({ route: '/assets?status=away' })

      await choose(() => {
        wrapper.findComponent(VBtnToggle).vm.$emit('update:modelValue', undefined)
      })

      expect(last(fetchAssets).status).toBe('away')
      expect(find('view-away').classes()).toContain('v-btn--active')
    })
  })

  describe('the search', () => {
    it('asks for the words typed, and keeps them in the address', async () => {
      const { wrapper, router, fetchAssets, choose } = await open()

      await choose(() => {
        wrapper.findComponent(AssetSearch).vm.$emit('update:modelValue', 'cam')
      })

      expect(last(fetchAssets).q).toBe('cam')
      expect(router.currentRoute.value.query).toEqual({ q: 'cam' })
      expect(wrapper.findComponent(AssetSearch).props('modelValue')).toBe('cam')
    })

    it('is filled in from the address', async () => {
      const { wrapper, fetchAssets } = await open({ route: '/assets?q=tv' })

      expect(last(fetchAssets).q).toBe('tv')
      expect(wrapper.findComponent(AssetSearch).props('modelValue')).toBe('tv')
    })

    describe('with the slash key', () => {
      const press = (init: KeyboardEventInit, target: EventTarget = window) => {
        const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })
        target.dispatchEvent(event)
        return event
      }

      it('goes to it from anywhere on the page', async () => {
        const { wrapper } = await open()

        const event = press({ key: '/' })

        expect(event.defaultPrevented).toBe(true)
        expect(document.activeElement).toBe(wrapper.find('input').element)
      })

      it('leaves the key alone in a field, so a slash can be typed', async () => {
        const { wrapper } = await open()
        const input = wrapper.find('input').element
        input.blur()

        const event = press({ key: '/' }, input)

        expect(event.defaultPrevented).toBe(false)
      })

      it('leaves other keys and shortcuts alone', async () => {
        await open()

        expect(press({ key: 'a' }).defaultPrevented).toBe(false)
        expect(press({ key: '/', ctrlKey: true }).defaultPrevented).toBe(false)
        expect(press({ key: '/', metaKey: true }).defaultPrevented).toBe(false)
        expect(press({ key: '/', altKey: true }).defaultPrevented).toBe(false)
      })

      it('stops listening when the page is left', async () => {
        const { wrapper } = await open()
        wrapper.unmount()

        expect(press({ key: '/' }).defaultPrevented).toBe(false)
      })
    })
  })

  describe('the other choices', () => {
    it('are listed by program, with how many each lists, and only for those that list any', async () => {
      const { find } = await open()

      expect(find('filter-source-opnsense').text()).toContain('Listed by OPNsense')
      expect(find('filter-source-opnsense').text()).toContain('3')
      expect(find('filter-source-ntopng').text()).toContain('2')
      expect(find('filter-source-wazuh').exists()).toBe(false)
    })

    it('narrow the list to a program, and back, each in the address', async () => {
      const { find, router, fetchAssets, choose } = await open()
      expect(find('filter-source-ntopng').attributes('aria-pressed')).toBe('false')

      await choose(() => find('filter-source-ntopng').trigger('click'))
      await choose(() => find('filter-source-opnsense').trigger('click'))

      expect(last(fetchAssets).sources).toEqual(['ntopng', 'opnsense'])
      expect(router.currentRoute.value.query).toEqual({ source: ['ntopng', 'opnsense'] })
      expect(find('filter-source-ntopng').attributes('aria-pressed')).toBe('true')

      await choose(() => find('filter-source-ntopng').trigger('click'))

      expect(last(fetchAssets).sources).toEqual(['opnsense'])
    })

    it('still show a program that was chosen and lists nothing, so it can be taken off', async () => {
      const { find } = await open({ route: '/assets?source=wazuh' })

      expect(find('filter-source-wazuh').attributes('aria-pressed')).toBe('true')
    })

    it('narrow the list to what is new, with how many are', async () => {
      const { find, router, fetchAssets, choose } = await open()
      expect(find('filter-new').text()).toContain('New this week')
      expect(find('filter-new').text()).toContain('1')

      await choose(() => find('filter-new').trigger('click'))

      expect(last(fetchAssets).new).toBe(true)
      expect(router.currentRoute.value.query).toEqual({ new: '1' })
      expect(find('filter-new').attributes('aria-pressed')).toBe('true')

      await choose(() => find('filter-new').trigger('click'))

      expect(last(fetchAssets).new).toBe(false)
    })

    it('narrow the list to what says nothing of what it is, with how many', async () => {
      const { find, fetchAssets, choose } = await open()
      expect(find('filter-unidentified').text()).toContain('Not identified')

      await choose(() => find('filter-unidentified').trigger('click'))

      expect(last(fetchAssets).unidentified).toBe(true)
      expect(find('filter-unidentified').attributes('aria-pressed')).toBe('true')

      await choose(() => find('filter-unidentified').trigger('click'))

      expect(last(fetchAssets).unidentified).toBe(false)
    })

    it('narrow the list to an interface, when any has networks, and back', async () => {
      const { wrapper, router, fetchAssets, choose } = await open()
      const select = () => wrapper.findAllComponents(VSelect)[0]!
      expect(select().props('label')).toBe('Interface')
      expect(select().props('modelValue')).toBe(0)

      await choose(() => {
        select().vm.$emit('update:modelValue', 5)
      })

      expect(last(fetchAssets).interface).toBe(5)
      expect(router.currentRoute.value.query).toEqual({ interface: '5' })
      expect(select().props('modelValue')).toBe(5)

      await choose(() => {
        select().vm.$emit('update:modelValue', 0)
      })

      expect(last(fetchAssets).interface).toBeUndefined()
      expect(router.currentRoute.value.query).toEqual({})
    })

    it('narrow the list to what the owner said it is, once they have said anything', async () => {
      const { wrapper, router, fetchAssets, choose } = await open({
        answer: page([asset()], {
          kinds: [{ key: 'camera', label: 'Camera or doorbell', count: 2 }],
          unclassified: 5,
        }),
      })
      const select = () =>
        wrapper.findAllComponents(VSelect).find((each) => each.props('label') === 'What it is')!
      expect(select().props('items')).toEqual([
        { value: '', title: 'Any kind' },
        { value: 'unclassified', title: 'Not classified (5)' },
        { value: 'camera', title: 'Camera or doorbell (2)' },
      ])
      expect(select().props('modelValue')).toBe('')

      await choose(() => {
        select().vm.$emit('update:modelValue', 'camera')
      })

      expect(last(fetchAssets).kind).toBe('camera')
      expect(router.currentRoute.value.query).toEqual({ kind: 'camera' })

      await choose(() => {
        select().vm.$emit('update:modelValue', '')
      })

      expect(last(fetchAssets).kind).toBeUndefined()
      expect(router.currentRoute.value.query).toEqual({})
    })

    it('keep the kind choice in view while it is chosen, so it can be taken off', async () => {
      const { wrapper } = await open({ route: '/assets?kind=unclassified' })

      expect(wrapper.findAllComponents(VSelect).map((select) => select.props('label'))).toContain(
        'What it is',
      )
    })

    it('have no interface to choose when none has networks', async () => {
      const { wrapper } = await open({ answer: page([asset()]) })

      expect(wrapper.findAllComponents(VSelect).map((select) => select.props('label'))).toEqual([
        'Order',
      ])
    })

    it('order the list, and say so in the address', async () => {
      const { wrapper, router, fetchAssets, choose } = await open()
      const select = () => wrapper.findAllComponents(VSelect).at(-1)!
      expect(select().props('label')).toBe('Order')
      expect(select().props('modelValue')).toBe('recent')

      await choose(() => {
        select().vm.$emit('update:modelValue', 'name')
      })

      expect(last(fetchAssets).sort).toBe('name')
      expect(router.currentRoute.value.query).toEqual({ sort: 'name' })
    })

    it('are cleared together, but not the state or the order', async () => {
      const { wrapper, find, router, fetchAssets, choose } = await open({
        route:
          '/assets?status=online&sort=name&q=lap&source=wazuh&new=1&unidentified=1&interface=4',
      })
      expect(wrapper.find('[data-test="page-description"]').text()).toContain('Every device')

      await choose(() => find('clear-filters').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({ status: 'online', sort: 'name' })
      expect(last(fetchAssets)).toMatchObject({ status: 'online', sort: 'name', sources: [] })
      expect(find('clear-filters').exists()).toBe(false)
    })

    it('can only be cleared while there is something to clear', async () => {
      const { find } = await open({ route: '/assets?status=online' })

      expect(find('clear-filters').exists()).toBe(false)
    })

    it('are ignored when the address has something that is not one of them', async () => {
      const { fetchAssets } = await open({ route: '/assets?status=asleep&sort=size&interface=x' })

      expect(last(fetchAssets)).toEqual({
        sources: [],
        new: false,
        unidentified: false,
        sort: 'recent',
        limit: 30,
        offset: 0,
      })
    })
  })

  describe('when there is no description to give', () => {
    it('gives the general one while it loads, and when a choice narrows the list', async () => {
      const { wrapper } = await open({ route: '/assets?q=lap' })

      expect(wrapper.find('[data-test="page-description"]').text()).toBe(
        'Every device your connected programs can see, as one list.',
      )
    })

    it('gives the general one when there are no assets', async () => {
      const { wrapper } = await open({
        answer: page([], { counts: counts({ all: 0, online: 0 }) }),
      })

      expect(wrapper.find('[data-test="page-description"]').text()).toContain('Every device')
    })
  })

  describe('when there is nothing to show', () => {
    const none = (overrides: Partial<assetsApi.AssetPage> = {}) =>
      page([], { counts: counts({ all: 0, online: 0 }), ...overrides })

    it('says nothing matches a choice, and clears the choices', async () => {
      const { find, router, choose } = await open({
        route: '/assets?q=zzz',
        answer: none({ counts: counts({ all: 3, online: 1, recent: 1, away: 1 }) }),
      })
      expect(find('assets-empty').text()).toContain('Nothing matches')

      await choose(() => find('empty-clear').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({})
    })

    it('says none are in a state when there are others, and shows them all', async () => {
      const { find, router, choose } = await open({
        route: '/assets?status=away',
        answer: none({ counts: counts({ all: 3, online: 1, recent: 1, away: 0 }) }),
      })
      const empty = find('assets-empty').text()
      expect(empty).toContain('None here')
      expect(empty).toContain(
        'No asset is in the \u201cNot seen for a while\u201d state. 3 in all.',
      )

      await choose(() => find('empty-all').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({})
    })

    it('says that nothing can list devices yet, and leads to the integrations', async () => {
      const { find } = await open({
        answer: none({
          suppliers: [supplier({ connected: false, assets: 0 })],
        }),
      })

      const empty = find('assets-empty').text()
      expect(empty).toContain('No devices yet')
      expect(empty).toContain('ARP table and DHCP leases')
      expect(find('empty-integrations').attributes('href')).toBe('/integrations')
      expect(find('asset-list').exists()).toBe(false)
    })

    it('says that what is connected has not listed any yet, and leads to the status', async () => {
      const { find } = await open({ answer: none() })

      const empty = find('assets-empty').text()
      expect(empty).toContain('Waiting for the first devices')
      expect(empty).toContain('OPNsense is connected, but nothing has listed a device yet')
      expect(find('empty-status').attributes('href')).toBe('/status')
    })

    it('names every program that is connected', async () => {
      const { find } = await open({
        answer: none({
          suppliers: [supplier(), supplier({ key: 'ntopng', name: 'ntopng' })],
        }),
      })

      expect(find('assets-empty').text()).toContain(
        'OPNsense and ntopng are connected, but nothing has listed a device yet',
      )
    })
  })

  describe('more of them', () => {
    function many(count: number, from = 0) {
      return Array.from({ length: count }, (_, number) =>
        asset({ key: `device-${from + number}`, name: `Device ${from + number}` }),
      )
    }

    it('are offered when there are more than were asked for', async () => {
      const first = many(30)
      const { find, text } = await open({
        answer: page(first, { total: 75, counts: counts({ all: 75, online: 75 }) }),
      })

      expect(text('more')).toContain('Showing 30 of 75.')
      expect(find('show-more').text()).toBe('Show 30 more')
    })

    it('say how many are left when that is fewer than a page', async () => {
      const { find } = await open({
        answer: page(many(30), { total: 42, counts: counts({ all: 42, online: 42 }) }),
      })

      expect(find('show-more').text()).toBe('Show 12 more')
    })

    it('are not offered when all are shown', async () => {
      const { find } = await open()

      expect(find('more').exists()).toBe(false)
    })

    it('are added to the end of the list, from where it stopped', async () => {
      const { find, names, fetchAssets, choose } = await open({
        answer: page(many(30), { total: 45, counts: counts({ all: 45, online: 45 }) }),
      })
      fetchAssets.mockResolvedValue(
        page(many(15, 30), { total: 45, counts: counts({ all: 45, online: 45 }) }),
      )

      await choose(() => find('show-more').trigger('click'))

      expect(last(fetchAssets)).toMatchObject({ limit: 30, offset: 30 })
      expect(names()).toHaveLength(45)
      expect(names().at(-1)).toBe('Device 44')
      expect(find('more').exists()).toBe(false)
    })

    it('say why they could not be added, and keep the ones shown', async () => {
      const { find, names, fetchAssets, choose } = await open({
        answer: page(many(30), { total: 45, counts: counts({ all: 45, online: 45 }) }),
      })
      fetchAssets.mockRejectedValue(offline())

      await choose(() => find('show-more').trigger('click'))

      expect(find('assets-stale').text()).toContain("Can't reach AresGate.")
      expect(names()).toHaveLength(30)
    })

    it('are all asked for again when the list is refreshed, so none vanish', async () => {
      const { find, fetchAssets, choose } = await open({
        answer: page(many(30), { total: 45, counts: counts({ all: 45, online: 45 }) }),
      })
      fetchAssets.mockResolvedValue(
        page(many(15, 30), { total: 45, counts: counts({ all: 45, online: 45 }) }),
      )
      await choose(() => find('show-more').trigger('click'))
      fetchAssets.mockResolvedValue(
        page(many(45), { total: 45, counts: counts({ all: 45, online: 45 }) }),
      )

      await choose(() => find('refresh').trigger('click'))

      expect(last(fetchAssets)).toMatchObject({ limit: 45, offset: 0 })
    })

    it('start again from the first page when a choice is made', async () => {
      const { find, fetchAssets, choose } = await open({
        answer: page(many(30), { total: 45, counts: counts({ all: 45, online: 45 }) }),
      })
      fetchAssets.mockResolvedValue(
        page(many(15, 30), { total: 45, counts: counts({ all: 45, online: 45 }) }),
      )
      await choose(() => find('show-more').trigger('click'))

      await choose(() => find('filter-new').trigger('click'))

      expect(last(fetchAssets)).toMatchObject({ limit: 30, offset: 0, new: true })
    })
  })

  describe('refreshing', () => {
    it('asks again when told to', async () => {
      const { find, fetchAssets, choose } = await open()

      await choose(() => find('refresh').trigger('click'))

      expect(fetchAssets).toHaveBeenCalledTimes(2)
    })

    it('asks again every half minute while the page is open, leaving what is on screen alone', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { fetchAssets, find } = await open()
        fetchAssets.mockReturnValue(new Promise(() => {}))

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(fetchAssets).toHaveBeenCalledTimes(2)
        expect(find('asset-list').exists()).toBe(true)
        expect(find('assets-loading').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    it('ignores the answer to a look that a newer one has replaced', async () => {
      const { find, fetchAssets, names, choose } = await open()
      let late: (answer: assetsApi.AssetPage) => void = () => {}
      fetchAssets.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      fetchAssets.mockResolvedValueOnce(page([asset({ name: 'Newer' })]))

      await choose(() => find('refresh').trigger('click'))
      await choose(() => find('refresh').trigger('click'))
      late(page([asset({ name: 'Older' })]))
      await flushPromises()

      expect(names()).toEqual(['Newer'])
    })

    it('ignores the failure of a look that a newer one has replaced', async () => {
      const { find, fetchAssets, choose } = await open()
      let fail: (reason: Error) => void = () => {}
      fetchAssets.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      await choose(() => find('refresh').trigger('click'))
      await choose(() => find('refresh').trigger('click'))

      fail(offline())
      await flushPromises()

      expect(find('assets-stale').exists()).toBe(false)
    })

    it('ignores the answer for more when a newer look has replaced it', async () => {
      const first = Array.from({ length: 30 }, (_, number) => asset({ key: `d-${number}` }))
      const { find, fetchAssets, names, choose } = await open({
        answer: page(first, { total: 45, counts: counts({ all: 45, online: 45 }) }),
      })
      let late: (answer: assetsApi.AssetPage) => void = () => {}
      fetchAssets.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      fetchAssets.mockResolvedValueOnce(page([asset({ name: 'Newer' })]))

      await choose(() => find('show-more').trigger('click'))
      await choose(() => find('refresh').trigger('click'))
      late(page([asset({ name: 'Too late' })], { total: 45 }))
      await flushPromises()

      expect(names()).toEqual(['Newer'])
    })

    it('ignores the failure to get more when a newer look has replaced it', async () => {
      const first = Array.from({ length: 30 }, (_, number) => asset({ key: `d-${number}` }))
      const { find, fetchAssets, choose } = await open({
        answer: page(first, { total: 45, counts: counts({ all: 45, online: 45 }) }),
      })
      let fail: (reason: Error) => void = () => {}
      fetchAssets.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      fetchAssets.mockResolvedValueOnce(page([asset({ name: 'Newer' })]))
      await choose(() => find('show-more').trigger('click'))
      await choose(() => find('refresh').trigger('click'))

      fail(offline())
      await flushPromises()

      expect(find('assets-stale').exists()).toBe(false)
    })
  })

  it('keeps showing a machine that no device matched', async () => {
    const { names, wrapper } = await open({ answer: page([machine()]) })

    expect(names()).toEqual(['build-server'])
    expect(wrapper.find('[data-test="asset-identity"]').text()).toBe('Wazuh agent · active')
  })
})
