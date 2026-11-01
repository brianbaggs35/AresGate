import { ApiError } from '@/api/client'
import * as interfacesApi from '@/api/interfaces'
import type { Listing } from '@/api/interfaces'
import FeedMove from '@/components/FeedMove.vue'
import InterfaceEditor from '@/components/InterfaceEditor.vue'
import { feed, iface, listing, overview, speed, stats } from '@/test/interfaces'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import InterfaceView from '@/views/InterfaceView.vue'

const TOKEN = 'a-security-token'

const PORT = feed({ id: 1, interface_id: 5 })
const INTERNET = iface({
  id: 5,
  name: 'Internet',
  role: 'internet',
  notes: 'Fibre from the street',
  networks: ['203.0.113.0/24'],
  feeds: [PORT, feed({ id: 2, interface_id: 5, native_name: 'igc1' })],
})
const LISTED: Listing = listing({
  interfaces: [INTERNET, iface({ id: 6, name: 'Home', role: 'home' })],
})

/** What is in the notice at the bottom of the page, which is outside the page itself. */
const notice = (selector: string) =>
  document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

async function open({
  result = LISTED,
  found = [stats({ interface_id: 5 })],
  id = 5,
}: { result?: Listing | Error; found?: ReturnType<typeof stats>[]; id?: number } = {}) {
  const list = vi.spyOn(interfacesApi, 'fetchInterfaces')
  if (result instanceof Error) list.mockRejectedValue(result)
  else list.mockResolvedValue(result)
  const fetchStats = vi.spyOn(interfacesApi, 'fetchOverview').mockResolvedValue(overview(found))
  const place = vi.spyOn(interfacesApi, 'placeFeed').mockResolvedValue(PORT)
  const mounted = await mountWithPlugins(InterfaceView, {
    signedIn: 'admin',
    route: `/interfaces/${id}`,
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, list, fetchStats, place, find }
}

describe('InterfaceView', () => {
  it('shows placeholders while it loads', async () => {
    vi.spyOn(interfacesApi, 'fetchInterfaces').mockReturnValue(new Promise(() => {}))
    vi.spyOn(interfacesApi, 'fetchOverview').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(InterfaceView, {
      signedIn: 'admin',
      route: '/interfaces/5',
    })

    expect(wrapper.find('[data-test="interface-loading"]').exists()).toBe(true)
  })

  it('says why it could not load, and tries again', async () => {
    const { find, list, wrapper } = await open({
      result: new ApiError(0, "Can't reach AresGate.", 'offline'),
    })
    expect(find('interface-error').text()).toContain("Can't reach AresGate.")
    list.mockResolvedValue(LISTED)

    await find('interface-retry').trigger('click')
    await flushPromises()

    expect(wrapper.find('h1').text()).toBe('Internet')
  })

  it('says so when the interface is not there, with a way back', async () => {
    const { find, wrapper } = await open({ id: 99 })

    expect(find('interface-missing').text()).toContain("That interface isn't there")
    expect(wrapper.find('[data-test="back"]').attributes('href')).toBe('/interfaces')
  })

  describe('what it shows', () => {
    it('names it, what it is for, and what the owner wrote about it', async () => {
      const { wrapper, find } = await open()

      expect(wrapper.find('h1').text()).toBe('Internet')
      expect(find('interface-role').text()).toBe('Internet')
      expect(wrapper.text()).toContain('Fibre from the street')
      expect(wrapper.find('[data-test="back"]').text()).toContain('Interfaces')
    })

    it('says what the role means when there are no notes', async () => {
      const { wrapper } = await open({
        result: listing({ interfaces: [{ ...INTERNET, notes: '' }] }),
      })
      expect(wrapper.text()).toContain('the link to your provider')
    })

    it('shows how fast it goes now, in both directions, and who measured it', async () => {
      const { find } = await open()

      expect(find('interface-tile-received').text()).toContain('2 Mb/s')
      expect(find('interface-tile-received').text()).toContain('From OPNsense')
      expect(find('interface-tile-sent').text()).toContain('400 kb/s')
    })

    it('counts its alerts and its devices', async () => {
      const { find } = await open()

      expect(find('interface-tile-alerts').text()).toContain('3')
      expect(find('interface-tile-alerts').text()).toContain('In the last 24 hours')
      expect(find('interface-tile-devices').text()).toContain('12')
      expect(find('interface-tile-devices').text()).toContain('On its networks')
    })

    it('says what is missing when nothing was measured and there are no networks to count in', async () => {
      const { find } = await open({
        found: [stats({ interface_id: 5, speed: null, devices: null })],
      })

      expect(find('interface-tile-received').text()).toContain('–')
      expect(find('interface-tile-received').text()).toContain('Nothing measured yet')
      expect(find('interface-tile-devices').text()).toContain('Add its networks to count them')
      expect(find('interface-chart').text()).toContain('No traffic measured yet')
    })

    it('shows a gap, not a number, when the overview has nothing for it yet', async () => {
      const { find } = await open({ found: [] })

      expect(find('interface-tile-received').text()).toContain('–')
      expect(find('interface-tile-alerts').text()).toContain('0')
      expect(find('interface-tile-devices').text()).toContain('–')
    })

    it('charts the traffic, received and sent', async () => {
      const { find } = await open()
      expect(find('interface-chart').text()).toContain('Speed through Internet')
    })

    it('lists its networks, when it has some', async () => {
      const { wrapper } = await open()
      expect(wrapper.findAll('[data-test="interface-network"]').map((chip) => chip.text())).toEqual(
        ['203.0.113.0/24'],
      )

      const bare = await open({ result: listing({ interfaces: [{ ...INTERNET, networks: [] }] }) })
      expect(bare.wrapper.find('[data-test="interface-network"]').exists()).toBe(false)
    })

    it('lists its data sources, each with a control to move it', async () => {
      const { wrapper } = await open()

      expect(
        wrapper.findAll('[data-test="interface-sources"] [data-test="feed-name"]').length,
      ).toBe(2)
      expect(wrapper.findAllComponents(FeedMove)[0]!.props('canCreate')).toBe(false)
    })

    it('says so when nothing is placed on it yet', async () => {
      const { find } = await open({ result: listing({ interfaces: [{ ...INTERNET, feeds: [] }] }) })
      expect(find('interface-no-sources').text()).toContain('Nothing is placed on this interface')
    })
  })

  describe('how far back', () => {
    it('is the last day to begin with, and can be the last week', async () => {
      const { fetchStats, wrapper, find } = await open()
      expect(fetchStats).toHaveBeenLastCalledWith('24h')

      const week = find('interface-window').findAll('button')[1]!
      await week.trigger('click')
      await flushPromises()

      expect(fetchStats).toHaveBeenLastCalledWith('7d')
      expect(wrapper.text()).toContain('In the last 7 days')
    })
  })

  describe('moving a data source', () => {
    it('puts it somewhere else, and says so with a way back', async () => {
      const { wrapper, place } = await open()

      wrapper.findAllComponents(FeedMove)[0]!.vm.$emit('move', { interface_id: 6 })
      await flushPromises()
      await flushPromises()

      expect(place).toHaveBeenCalledWith(1, { interface_id: 6 }, TOKEN)
      expect(notice('undo-notice-text')?.textContent).toBe('OPNsense igc0 is now on Home.')
    })

    it('takes it back when asked', async () => {
      const { wrapper, place } = await open()
      wrapper.findAllComponents(FeedMove)[0]!.vm.$emit('move', { ignored: true })
      await flushPromises()
      await flushPromises()
      place.mockClear()

      notice('undo-notice-undo')?.click()
      await flushPromises()
      await flushPromises()

      expect(place).toHaveBeenCalledWith(1, { interface_id: 5, ignored: false }, TOKEN)
      expect(notice('undo-notice-text')?.textContent).toBe('Taken back.')
    })

    it('says why it could not', async () => {
      const { wrapper, place, find } = await open()
      place.mockRejectedValue(new ApiError(404, 'That feed is not there.', 'x'))

      wrapper.findAllComponents(FeedMove)[0]!.vm.$emit('move', { interface_id: 6 })
      await flushPromises()
      await flushPromises()

      expect(find('interface-problem').text()).toBe('That feed is not there.')
    })
  })

  describe('editing', () => {
    it('opens the editor on this interface', async () => {
      const { find, wrapper } = await open()

      await find('interface-edit').trigger('click')

      const editor = wrapper.findComponent(InterfaceEditor)
      expect(editor.props('modelValue')).toBe(true)
      expect(editor.props('interface')).toEqual(INTERNET)
    })

    it('reads it again and says so when it was saved', async () => {
      const { wrapper, list } = await open()

      wrapper.findComponent(InterfaceEditor).vm.$emit('saved', 'Internet saved.')
      await flushPromises()
      await flushPromises()

      expect(list).toHaveBeenCalledTimes(2)
      expect(notice('undo-notice-text')?.textContent).toBe('Internet saved.')
    })

    it('goes back to the list when it was removed', async () => {
      const { wrapper, router } = await open()

      wrapper.findComponent(InterfaceEditor).vm.$emit('removed', 'Internet removed.')
      await vi.waitFor(() => {
        expect(router.currentRoute.value.name).toBe('interfaces')
      })
    })
  })

  it('shows speeds from ntopng as ntopng’s', async () => {
    const { find } = await open({
      found: [
        stats({ interface_id: 5, speed: speed({ source: 'ntopng', source_name: 'ntopng' }) }),
      ],
    })
    expect(find('interface-tile-received').text()).toContain('From ntopng')
  })
})
