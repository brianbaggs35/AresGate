import { ApiError } from '@/api/client'
import * as interfacesApi from '@/api/interfaces'
import type { Listing } from '@/api/interfaces'
import FeedMove from '@/components/FeedMove.vue'
import InterfaceCard from '@/components/InterfaceCard.vue'
import InterfaceEditor from '@/components/InterfaceEditor.vue'
import SuggestionCard from '@/components/SuggestionCard.vue'
import { feed, iface, listing, overview, stats, suggestion } from '@/test/interfaces'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import InterfacesView from '@/views/InterfacesView.vue'

const TOKEN = 'a-security-token'

const INTERNET = iface({ id: 5, name: 'Internet', feeds: [feed({ id: 1, interface_id: 5 })] })
const WAITING = feed({ id: 2, native_name: 'igc2' })
const ALSO = feed({ id: 3, native_name: 'igc3', integration_name: 'ntopng', label: 'LAN (eth3)' })
const ASIDE = feed({ id: 4, native_name: 'lo0', ignored: true })

const FULL: Listing = listing({
  interfaces: [INTERNET],
  unplaced: [WAITING, ALSO],
  ignored: [ASIDE],
  suggestions: [suggestion({ feed_ids: [2, 3] })],
})

/** What is in the notice at the bottom of the page, which is outside the page itself. */
const notice = (selector: string) =>
  document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

async function open(result: Listing | Error = FULL) {
  const list = vi.spyOn(interfacesApi, 'fetchInterfaces')
  if (result instanceof Error) list.mockRejectedValue(result)
  else list.mockResolvedValue(result)
  vi.spyOn(interfacesApi, 'fetchOverview').mockResolvedValue(overview([stats({ interface_id: 5 })]))
  const place = vi.spyOn(interfacesApi, 'placeFeed').mockResolvedValue(WAITING)
  const create = vi.spyOn(interfacesApi, 'createInterface').mockResolvedValue(iface({ id: 8 }))
  const remove = vi.spyOn(interfacesApi, 'removeInterface').mockResolvedValue(undefined)
  const discover = vi
    .spyOn(interfacesApi, 'discoverFeeds')
    .mockResolvedValue({ new: 2, complete: true, notes: [] })
  const mounted = await mountWithPlugins(InterfacesView, { signedIn: 'admin' })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, list, place, create, remove, discover, find, click }
}

describe('InterfacesView', () => {
  it('shows placeholders while it loads', async () => {
    vi.spyOn(interfacesApi, 'fetchInterfaces').mockReturnValue(new Promise(() => {}))
    vi.spyOn(interfacesApi, 'fetchOverview').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(InterfacesView, { signedIn: 'admin' })

    expect(wrapper.find('[data-test="interfaces-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="interfaces-hero"]').exists()).toBe(false)
  })

  it('says why it could not load, and tries again', async () => {
    const { find, click, list } = await open(new ApiError(0, "Can't reach AresGate.", 'offline'))

    expect(find('interfaces-error').text()).toContain("Can't reach AresGate.")
    expect(find('interfaces-hero').exists()).toBe(false)
    list.mockResolvedValue(FULL)

    await click('interfaces-retry')

    expect(find('interfaces-hero').exists()).toBe(true)
  })

  it('has a heading and says what the page is for', async () => {
    const { wrapper } = await open()

    expect(wrapper.find('h1').text()).toBe('Interfaces')
    expect(wrapper.text()).toContain('Place what each program reports')
  })

  it('says how much is left to decide, first', async () => {
    const { find } = await open()

    expect(find('interfaces-hero-title').text()).toBe('2 feeds need a decision')
    expect(find('interfaces-hero-eyebrow').text()).toBe('Needs a decision')
  })

  it('says there is nothing yet when there is nothing', async () => {
    const { find, wrapper } = await open(listing())

    expect(find('interfaces-hero-title').text()).toBe('No interfaces yet')
    expect(find('interfaces-find').text()).toBe('Find interfaces')
    for (const section of ['suggestions', 'grid', 'unplaced', 'ignored']) {
      expect(wrapper.find(`[data-test="interfaces-${section}"]`).exists()).toBe(false)
    }
  })

  it('says everything is placed once it is', async () => {
    const { find } = await open(listing({ interfaces: [INTERNET] }))
    expect(find('interfaces-hero-title').text()).toBe('1 interface, every feed placed')
  })

  describe('the interfaces', () => {
    it('has a card for each, with what it has been doing', async () => {
      const { wrapper } = await open()

      const cards = wrapper.findAllComponents(InterfaceCard)
      expect(cards).toHaveLength(1)
      expect(cards[0]!.props('item')).toEqual(INTERNET)
      expect(cards[0]!.props('stats')?.interface_id).toBe(5)
    })

    it('has a card without numbers for one that the overview does not know yet', async () => {
      const { wrapper } = await open({
        ...FULL,
        interfaces: [INTERNET, iface({ id: 6, name: 'Home' })],
      })

      const cards = wrapper.findAllComponents(InterfaceCard)
      expect(cards.map((card) => card.props('stats')?.interface_id)).toEqual([5, undefined])
    })
  })

  describe('the suggestions', () => {
    it('are listed with the feeds they name', async () => {
      const { wrapper } = await open()

      const cards = wrapper.findAllComponents(SuggestionCard)
      expect(cards).toHaveLength(1)
      expect(cards[0]!.props('feeds').map((each) => each.id)).toEqual([2, 3])
    })

    it('are confirmed, which makes the interface and says so, with a way to take it back', async () => {
      const { wrapper, create, remove } = await open()

      wrapper.findComponent(SuggestionCard).vm.$emit('confirm')
      await flushPromises()
      await flushPromises()

      expect(create).toHaveBeenCalledWith({ name: 'Guests', role: 'guest', feeds: [2, 3] }, TOKEN)
      expect(notice('undo-notice-text')?.textContent).toBe('2 feeds placed on Guests.')

      notice('undo-notice-undo')?.click()
      await flushPromises()
      await flushPromises()

      expect(remove).toHaveBeenCalledWith(8, TOKEN)
      expect(notice('undo-notice-text')?.textContent).toBe('Taken back.')
    })

    it('are ignored, which sets their feeds aside', async () => {
      const { wrapper, place } = await open()

      wrapper.findComponent(SuggestionCard).vm.$emit('ignore')
      await flushPromises()
      await flushPromises()

      expect(place.mock.calls.map(([id, placement]) => [id, placement])).toEqual([
        [2, { ignored: true }],
        [3, { ignored: true }],
      ])
      expect(notice('undo-notice-text')?.textContent).toBe('2 feeds set aside.')
    })

    it('are changed in the editor, which starts as the suggestion said', async () => {
      const { wrapper } = await open()

      wrapper.findComponent(SuggestionCard).vm.$emit('change')
      await flushPromises()

      const editor = wrapper.findComponent(InterfaceEditor)
      expect(editor.props('modelValue')).toBe(true)
      expect(editor.props('interface')).toBeNull()
      expect(editor.props('starter')).toEqual({ name: 'Guests', role: 'guest', feeds: [2, 3] })
    })

    it('can all be confirmed at once, when there are several', async () => {
      const several = {
        ...FULL,
        suggestions: [
          suggestion({ name: 'Guests', feed_ids: [2] }),
          suggestion({ name: 'Cameras', role: 'iot', feed_ids: [3] }),
        ],
      }
      const { click, create } = await open(several)

      await click('suggestions-confirm-all')

      expect(create).toHaveBeenCalledTimes(2)
      expect(notice('undo-notice-text')?.textContent).toBe('2 feeds placed on 2 interfaces.')
    })

    it('can only be confirmed all at once when there are several', async () => {
      const { find } = await open()
      expect(find('suggestions-confirm-all').exists()).toBe(false)
    })
  })

  describe('feeds that are not placed', () => {
    it('are listed, each with a control to place it', async () => {
      const { find, wrapper } = await open()

      expect(find('interfaces-unplaced').text()).toContain('2 feeds have not been placed')
      expect(
        wrapper.findAll('[data-test="interfaces-unplaced"] [data-test="feed-name"]'),
      ).toHaveLength(2)
    })

    it('say it in the singular for one', async () => {
      const { find } = await open({ ...FULL, unplaced: [WAITING], suggestions: [] })
      expect(find('interfaces-unplaced').text()).toContain('1 feed has not been placed')
    })

    it('are placed on an interface, which says so with a way to take it back', async () => {
      const { wrapper, place } = await open()

      wrapper.findAllComponents(FeedMove)[0]!.vm.$emit('move', { interface_id: 5 })
      await flushPromises()
      await flushPromises()

      expect(place).toHaveBeenCalledWith(2, { interface_id: 5 }, TOKEN)
      expect(notice('undo-notice-text')?.textContent).toBe('OPNsense igc2 is now on Internet.')
    })

    it('can start a new interface, named for the feed', async () => {
      const { wrapper } = await open()
      const moves = wrapper.findAllComponents(FeedMove)

      moves[0]!.vm.$emit('create')
      await flushPromises()
      expect(wrapper.findComponent(InterfaceEditor).props('starter')).toEqual({
        name: 'igc2',
        role: 'home',
        feeds: [2],
      })

      moves[1]!.vm.$emit('create')
      await flushPromises()
      expect(wrapper.findComponent(InterfaceEditor).props('starter')?.name).toBe('LAN (eth3)')
    })

    it('start a new interface named for the program when the feed has no name', async () => {
      const bare = feed({ id: 7, native_name: '', label: '', integration_name: 'CrowdSec' })
      const { wrapper } = await open({ ...FULL, unplaced: [bare], suggestions: [] })

      wrapper.findComponent(FeedMove).vm.$emit('create')
      await flushPromises()

      expect(wrapper.findComponent(InterfaceEditor).props('starter')?.name).toBe('CrowdSec')
    })

    it('say why a move failed, and the page is read again', async () => {
      const { wrapper, find, place, list } = await open()
      place.mockRejectedValue(new ApiError(404, 'That feed is not there.', 'x'))

      wrapper.findAllComponents(FeedMove)[0]!.vm.$emit('move', { interface_id: 5 })
      await flushPromises()
      await flushPromises()

      expect(find('interfaces-problem').text()).toBe('That feed is not there.')
      expect(list).toHaveBeenCalledTimes(2)
    })
  })

  describe('feeds that were set aside', () => {
    it('are listed apart, and can be brought back by placing them', async () => {
      const { find, wrapper, place } = await open()

      expect(find('interfaces-ignored').text()).toContain('Set aside (1)')
      await wrapper.find('.v-expansion-panel-title').trigger('click')
      await flushPromises()
      const moves = wrapper.findAllComponents(FeedMove)
      moves.at(-1)!.vm.$emit('move', { interface_id: 5 })
      await flushPromises()
      await flushPromises()

      expect(place).toHaveBeenCalledWith(4, { interface_id: 5 }, TOKEN)
    })

    it('can start a new interface too', async () => {
      const { wrapper } = await open()
      await wrapper.find('.v-expansion-panel-title').trigger('click')
      await flushPromises()

      wrapper.findAllComponents(FeedMove).at(-1)!.vm.$emit('create')
      await flushPromises()

      expect(wrapper.findComponent(InterfaceEditor).props('starter')?.feeds).toEqual([4])
    })
  })

  describe('adding an interface', () => {
    it('opens the editor with nothing in it', async () => {
      const { click, wrapper } = await open()

      await click('interfaces-add')

      const editor = wrapper.findComponent(InterfaceEditor)
      expect(editor.props('modelValue')).toBe(true)
      expect(editor.props('interface')).toBeNull()
      expect(editor.props('starter')).toBeNull()
    })

    it('cannot when there are as many as there can be', async () => {
      const { find } = await open({ ...FULL, max_interfaces: 1 })
      expect(find('interfaces-add').attributes('disabled')).toBeDefined()
    })

    it('reads everything again and says so when one was saved', async () => {
      const { wrapper, list } = await open()

      wrapper.findComponent(InterfaceEditor).vm.$emit('saved', 'Guests added.')
      await flushPromises()
      await flushPromises()

      expect(list).toHaveBeenCalledTimes(2)
      expect(notice('undo-notice-text')?.textContent).toBe('Guests added.')
      expect(notice('undo-notice-undo')).toBeNull()
    })
  })

  describe('finding feeds', () => {
    it('looks, and says how many were found', async () => {
      const { click, find, discover } = await open()

      await click('interfaces-find')

      expect(discover).toHaveBeenCalledWith(TOKEN)
      expect(find('interfaces-found').text()).toContain('Found 2 new feeds.')
    })

    it('says one in the singular, and nothing when there is nothing', async () => {
      const { click, find, discover } = await open()
      discover.mockResolvedValue({ new: 1, complete: true, notes: [] })
      await click('interfaces-find')
      expect(find('interfaces-found').text()).toContain('Found 1 new feed.')

      discover.mockResolvedValue({ new: 0, complete: true, notes: [] })
      await click('interfaces-find')
      expect(find('interfaces-found').text()).toContain('Nothing new was found.')
    })

    it('says what could not be asked, and when the search was cut short', async () => {
      const { click, find, discover } = await open()
      discover.mockResolvedValue({
        new: 0,
        complete: false,
        notes: ['ntopng couldn’t list its interfaces.'],
      })

      await click('interfaces-find')

      expect(find('interfaces-found-partial').text()).toContain('took too long')
      expect(find('interfaces-note').text()).toBe('ntopng couldn’t list its interfaces.')
    })

    it('can be dismissed', async () => {
      const { click, find, wrapper } = await open()
      await click('interfaces-find')

      await wrapper.find('[data-test="interfaces-found"] .v-alert__close button').trigger('click')

      expect(find('interfaces-found').exists()).toBe(false)
    })

    it('says why it could not', async () => {
      const { click, find, discover } = await open()
      discover.mockRejectedValue(new ApiError(500, 'It broke.', 'x'))

      await click('interfaces-find')

      expect(find('interfaces-problem').text()).toBe('It broke.')
      expect(find('interfaces-found').exists()).toBe(false)
    })
  })
})
