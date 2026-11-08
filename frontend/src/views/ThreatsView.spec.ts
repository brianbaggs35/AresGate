import { ApiError } from '@/api/client'
import * as incidentsApi from '@/api/incidents'
import * as threatsApi from '@/api/threats'
import { incident, page } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { family, funnel, overview } from '@/test/threats'
import ThreatsView from '@/views/ThreatsView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

interface Options {
  found?: threatsApi.Overview | Error
  route?: string
  incidents?: incidentsApi.IncidentPage
}

async function open({ found = overview(), route = '/threats', incidents }: Options = {}) {
  const fetchOverview = vi.spyOn(threatsApi, 'fetchOverview')
  if (found instanceof Error) fetchOverview.mockRejectedValue(found)
  else fetchOverview.mockResolvedValue(found)
  const fetchIncidents = vi
    .spyOn(incidentsApi, 'fetchIncidents')
    .mockResolvedValue(incidents ?? page([incident({ id: 1 }), incident({ id: 2 })]))
  const mounted = await mountWithPlugins(ThreatsView, { signedIn: 'admin', withApp: true, route })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, fetchOverview, fetchIncidents, find }
}

describe('ThreatsView', () => {
  it('shows a skeleton until the answer arrives', async () => {
    vi.spyOn(threatsApi, 'fetchOverview').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(ThreatsView, {
      signedIn: 'admin',
      route: '/threats',
    })

    expect(wrapper.find('[data-test="threats-loading"]').exists()).toBe(true)
  })

  it('asks for the last 24 hours, and the threats, the surest first', async () => {
    const { fetchOverview, fetchIncidents } = await open()

    expect(fetchOverview).toHaveBeenCalledWith('24h')
    expect(fetchIncidents).toHaveBeenCalledWith({
      lanes: ['threat'],
      q: `since:${overview().window.start}`,
      order: 'priority',
      limit: 20,
    })
  })

  it('says how the reports came down to threats and what has been judged', async () => {
    const { find } = await open()

    expect(find('funnel-sentence').text()).toContain('70,412 reports')
    expect(find('coverage').text()).toBe('7 of 9 kinds have been judged. 2 are waiting for the AI.')
    expect(find('kinds-link').attributes('href')).toBe('/threats/kinds')
    expect(find('tune-link').attributes('href')).toBe('/settings/threat-detection')
  })

  it('counts each lane, and says what the one on screen is', async () => {
    const { find } = await open()

    expect(find('count-threat').text()).toBe('2')
    expect(find('count-suspect').text()).toBe('5')
    expect(find('count-background').text()).toBe('50')
    expect(find('lane-meaning').text()).toContain('Highly likely to be a real attack')
  })

  it('lists the threats as cards', async () => {
    const { find } = await open()

    expect(find('lane-list').findAll('[data-test="incident-card"]')).toHaveLength(2)
  })

  it('opens on the suspects when there are no threats', async () => {
    const { fetchIncidents } = await open({ found: overview({ funnel: funnel({ threats: 0 }) }) })

    expect(fetchIncidents).toHaveBeenCalledWith(expect.objectContaining({ lanes: ['suspect'] }))
  })

  it('opens on the lane in the address of the page', async () => {
    const { fetchIncidents } = await open({ route: '/threats?lane=suspect' })

    expect(fetchIncidents).toHaveBeenCalledWith(expect.objectContaining({ lanes: ['suspect'] }))
  })

  it('ignores a lane it does not know', async () => {
    const { fetchIncidents } = await open({ route: '/threats?lane=other' })

    expect(fetchIncidents).toHaveBeenCalledWith(expect.objectContaining({ lanes: ['threat'] }))
  })

  it('moves to another lane by putting it in the address', async () => {
    const { find, router, fetchIncidents } = await open()

    await find('lane-suspect').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ lane: 'suspect' })
    expect(fetchIncidents).toHaveBeenLastCalledWith(expect.objectContaining({ lanes: ['suspect'] }))
  })

  it('asks again for another range', async () => {
    const { find, fetchOverview } = await open()

    await find('range-7d').trigger('click')
    await flushPromises()

    expect(fetchOverview).toHaveBeenLastCalledWith('7d')
  })

  it('asks again on request', async () => {
    const { find, fetchOverview } = await open()

    await find('refresh').trigger('click')
    await flushPromises()

    expect(fetchOverview).toHaveBeenCalledTimes(2)
  })

  describe('with nothing in the lane', () => {
    it('says there are no threats', async () => {
      const { find } = await open({ incidents: page([]) })

      expect(find('lane-empty').text()).toContain('No threats')
      expect(find('lane-empty').text()).toContain('looks like a real attack')
    })

    it('says there are no suspects', async () => {
      const { find } = await open({ incidents: page([]), route: '/threats?lane=suspect' })

      expect(find('lane-empty').text()).toContain('No suspects')
    })
  })

  describe('showing more', () => {
    it('adds the next page, until all are shown', async () => {
      const { find, fetchIncidents, wrapper } = await open({
        incidents: page([incident({ id: 1 })], { total: 3 }),
      })
      expect(find('more').text()).toBe('Show more (2 left)')
      fetchIncidents.mockResolvedValue(
        page([incident({ id: 2 }), incident({ id: 3 })], { total: 3 }),
      )

      await find('more').trigger('click')
      await flushPromises()

      expect(fetchIncidents).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 1 }))
      expect(wrapper.findAll('[data-test="incident-card"]')).toHaveLength(3)
      expect(find('more').exists()).toBe(false)
    })

    it('says why more could not be shown', async () => {
      const { find, fetchIncidents, wrapper } = await open({
        incidents: page([incident({ id: 1 })], { total: 3 }),
      })
      fetchIncidents.mockRejectedValue(offline())

      await find('more').trigger('click')
      await flushPromises()

      expect(find('more-error').text()).toBe("Can't reach AresGate.")
      expect(wrapper.findAll('[data-test="incident-card"]')).toHaveLength(1)
    })
  })

  describe('the background', () => {
    it('lists the kinds that were set aside, not thousands of incidents', async () => {
      const { find, fetchIncidents, wrapper } = await open({ route: '/threats?lane=background' })

      expect(fetchIncidents).not.toHaveBeenCalled()
      expect(find('kind-list').findAll('[data-test="family-card"]')).toHaveLength(1)
      expect(wrapper.findAll('[data-test="incident-card"]')).toHaveLength(0)
      expect(find('lane-meaning').text()).toContain('out of your way')
    })

    it('leads to every kind and to the incidents', async () => {
      const { find } = await open({ route: '/threats?lane=background' })

      expect(find('all-kinds').attributes('href')).toBe('/threats/kinds')
      expect(find('background-incidents').attributes('href')).toBe('/incidents?lane=background')
    })

    it('says when there is nothing in it', async () => {
      const { find } = await open({
        route: '/threats?lane=background',
        found: overview({ families: [] }),
      })

      expect(find('kind-empty').exists()).toBe(true)
    })

    it('shows the kinds again when it is moved to from another lane', async () => {
      const { find } = await open({ found: overview({ families: [family({ id: 9 })] }) })

      await find('lane-background').trigger('click')
      await flushPromises()

      expect(find('kind-list').exists()).toBe(true)
      expect(find('lane-list').exists()).toBe(false)
    })
  })

  describe('a verdict from a card', () => {
    it('asks again, since the incident can leave the lane', async () => {
      const { wrapper, fetchOverview } = await open()

      wrapper.findComponent({ name: 'IncidentCard' }).vm.$emit('judged', {
        kind: 'low_priority',
        scope: { label: 'x' },
        rule: { replaced: null },
      })
      await flushPromises()

      expect(fetchOverview).toHaveBeenCalledTimes(2)
    })

    it('asks again when a verdict is taken back, since the incident comes back', async () => {
      const { wrapper, fetchOverview } = await open()

      wrapper.findComponent({ name: 'JudgedNotice' }).vm.$emit('undone')
      await flushPromises()

      expect(fetchOverview).toHaveBeenCalledTimes(2)
    })
  })

  it('drops the failure of a load that a newer one has taken the place of', async () => {
    let fail: (reason: Error) => void = () => {}
    const fetchOverview = vi.spyOn(threatsApi, 'fetchOverview')
    fetchOverview.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
    fetchOverview.mockResolvedValue(overview())
    vi.spyOn(incidentsApi, 'fetchIncidents').mockResolvedValue(page([incident({ id: 1 })]))
    const { router, wrapper } = await mountWithPlugins(ThreatsView, {
      signedIn: 'admin',
      withApp: true,
      route: '/threats',
    })
    await router.replace({ query: { lane: 'suspect' } })
    await flushPromises()

    fail(offline())
    await flushPromises()

    expect(wrapper.find('[data-test="threats-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="threats-stale"]').exists()).toBe(false)
  })

  describe('when it cannot be loaded', () => {
    it('says so, and tries again', async () => {
      const { find, fetchOverview } = await open({ found: offline() })

      expect(find('threats-error').text()).toContain("Can't reach AresGate.")

      fetchOverview.mockResolvedValue(overview())
      await find('retry').trigger('click')
      await flushPromises()

      expect(find('threats-error').exists()).toBe(false)
      expect(find('funnel-card').exists()).toBe(true)
    })

    it('says it when the incidents of the lane cannot be read', async () => {
      vi.spyOn(threatsApi, 'fetchOverview').mockResolvedValue(overview())
      vi.spyOn(incidentsApi, 'fetchIncidents').mockRejectedValue(offline())
      const { wrapper } = await mountWithPlugins(ThreatsView, {
        signedIn: 'admin',
        route: '/threats',
      })
      await flushPromises()

      expect(wrapper.find('[data-test="threats-error"]').exists()).toBe(true)
    })

    it('keeps what it has while a refresh fails, and says so', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, fetchOverview } = await open()
        fetchOverview.mockRejectedValue(offline())

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(find('threats-stale').text()).toContain("Can't reach AresGate.")
        expect(find('funnel-card').exists()).toBe(true)

        fetchOverview.mockResolvedValue(overview())
        vi.advanceTimersByTime(30_000)
        await flushPromises()
        expect(find('threats-stale').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    it('drops the answer to an older question', async () => {
      const { find, fetchOverview } = await open()
      let late: (found: threatsApi.Overview) => void = () => {}
      fetchOverview.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      fetchOverview.mockResolvedValueOnce(overview({ funnel: funnel({ threats: 9 }) }))

      await find('refresh').trigger('click')
      await find('refresh').trigger('click')
      await flushPromises()
      late(overview({ funnel: funnel({ threats: 1 }) }))
      await flushPromises()

      expect(find('count-threat').text()).toBe('9')
    })
  })
})
