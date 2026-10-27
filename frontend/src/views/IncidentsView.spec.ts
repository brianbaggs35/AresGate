import type { VueWrapper } from '@vue/test-utils'
import { VBtnToggle, VSelect } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as incidentsApi from '@/api/incidents'
import * as verdictsApi from '@/api/verdicts'
import { useSessionStore } from '@/stores/session'
import { incident, page } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { given } from '@/test/verdicts'
import IncidentsView from '@/views/IncidentsView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

/** Three incidents: one open, one being looked at, one over. */
function some() {
  return page(
    [
      incident({ id: 3, title: 'Port scan (198.51.100.7)', severity: 'critical' }),
      incident({ id: 2, title: 'Brute force on ssh (203.0.113.9)', status: 'investigating' }),
    ],
    { counts: { open: 1, investigating: 1, resolved: 1, dismissed: 0 }, total: 2 },
  )
}

interface Options {
  route?: string
  answer?: incidentsApi.IncidentPage | Error
}

async function open({ route = '/incidents', answer = some() }: Options = {}) {
  const fetchIncidents = vi.spyOn(incidentsApi, 'fetchIncidents')
  if (answer instanceof Error) fetchIncidents.mockRejectedValue(answer)
  else fetchIncidents.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(IncidentsView, { signedIn: 'admin', withApp: true, route })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const titles = () =>
    mounted.wrapper.findAll('[data-test="incident-title"]').map((title) => title.text())
  /** Does what someone does to the filters, and waits for the new address of the page (which
   * takes a moment to arrive) and for the list to be asked for again. */
  const choose = async (act: () => unknown) => {
    await act()
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, fetchIncidents, find, text, titles, choose }
}

function last(fetchIncidents: { mock: { calls: unknown[][] } }) {
  return fetchIncidents.mock.calls.at(-1)?.[0] as incidentsApi.IncidentQuery
}

describe('IncidentsView', () => {
  it('asks for the incidents that are open or being looked at', async () => {
    const { fetchIncidents } = await open()

    expect(fetchIncidents).toHaveBeenCalledTimes(1)
    expect(last(fetchIncidents)).toEqual({
      statuses: ['open', 'investigating'],
      verdicts: ['none', 'threat'],
      minConfidence: 0,
      limit: 25,
    })
  })

  it('shows a skeleton until the first answer arrives', async () => {
    vi.spyOn(incidentsApi, 'fetchIncidents').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(IncidentsView, { signedIn: 'admin' })

    expect(wrapper.find('[data-test="incidents-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="incident-list"]').exists()).toBe(false)
  })

  it('lists them as they were sent, most urgent first', async () => {
    const { titles, find } = await open()

    expect(titles()).toEqual(['Port scan (198.51.100.7)', 'Brute force on ssh (203.0.113.9)'])
    expect(find('incidents-empty').exists()).toBe(false)
  })

  it('counts the incidents in each view, from every incident there is', async () => {
    const { text } = await open()

    expect(text('count-active')).toBe('2')
    expect(text('count-open')).toBe('1')
    expect(text('count-investigating')).toBe('1')
    expect(text('count-resolved')).toBe('1')
    expect(text('count-dismissed')).toBe('0')
    expect(text('count-all')).toBe('3')
  })

  it('says when the numbers on screen arrived', async () => {
    const { text } = await open()

    expect(text('updated')).toMatch(/^Updated \d/)
    expect(text('updated')).toContain('every 30 seconds')
  })

  describe('the views', () => {
    it('start from the active ones, with nothing in the address of the page', async () => {
      const { find, router } = await open()

      expect(find('view-active').classes()).toContain('v-btn--active')
      expect(router.currentRoute.value.query).toEqual({})
    })

    it('ask for the others, and say so in the address, so a link brings them back', async () => {
      const { find, router, fetchIncidents, choose } = await open()

      await choose(() => find('view-resolved').trigger('click'))

      expect(last(fetchIncidents).statuses).toEqual(['resolved'])
      expect(router.currentRoute.value.query).toEqual({ view: 'resolved' })
      expect(find('view-resolved').classes()).toContain('v-btn--active')
    })

    it('ask for all of them with no status', async () => {
      const { find, fetchIncidents, choose } = await open()

      await choose(() => find('view-all').trigger('click'))

      expect(last(fetchIncidents).statuses).toEqual([])
    })

    it('go back to the first when the first is chosen again', async () => {
      const { find, router, choose } = await open({ route: '/incidents?view=dismissed' })

      await choose(() => find('view-active').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({})
    })

    it('stay as they are when none is chosen', async () => {
      const { wrapper, fetchIncidents, choose } = await open({ route: '/incidents?view=open' })

      await choose(() => {
        wrapper.findComponent(VBtnToggle).vm.$emit('update:modelValue', undefined)
      })

      expect(fetchIncidents).toHaveBeenCalledTimes(1)
    })

    it('come from the address of the page', async () => {
      const { find, fetchIncidents } = await open({ route: '/incidents?view=investigating' })

      expect(last(fetchIncidents).statuses).toEqual(['investigating'])
      expect(find('view-investigating').classes()).toContain('v-btn--active')
    })

    it('start again from the top, dropping what was listed for the others', async () => {
      const { find, fetchIncidents, titles, choose } = await open()
      fetchIncidents.mockResolvedValue(
        page([incident({ id: 9, title: 'Old news (192.0.2.4)', status: 'resolved' })]),
      )

      await choose(() => find('view-resolved').trigger('click'))

      expect(titles()).toEqual(['Old news (192.0.2.4)'])
    })
  })

  describe('the filters', () => {
    /** Chooses from the select that is at this place on the page. */
    const pick = (wrapper: VueWrapper, at: number, value: unknown) =>
      wrapper.findAllComponents(VSelect)[at]?.vm.$emit('update:modelValue', value)

    it('narrow the list to the serious ones', async () => {
      const { wrapper, router, fetchIncidents, choose } = await open()

      await choose(() => pick(wrapper, 0, 'high'))

      expect(last(fetchIncidents).minSeverity).toBe('high')
      expect(router.currentRoute.value.query).toEqual({ severity: 'high' })
    })

    it('narrow it to the incidents AresGate is sure of', async () => {
      const { wrapper, router, fetchIncidents, choose } = await open()

      await choose(() => pick(wrapper, 1, 65))

      expect(last(fetchIncidents).minConfidence).toBe(65)
      expect(router.currentRoute.value.query).toEqual({ confidence: '65' })
    })

    it('come from the address of the page, and ignore what is not a choice', async () => {
      const { fetchIncidents, find, wrapper } = await open({
        route: '/incidents?severity=high&confidence=35&view=nonsense',
      })

      expect(last(fetchIncidents)).toMatchObject({
        statuses: ['open', 'investigating'],
        minSeverity: 'high',
        minConfidence: 35,
      })
      expect(find('clear-filters').exists()).toBe(true)
      expect(wrapper.findAllComponents(VSelect)[0]?.props('modelValue')).toBe('high')
    })

    it('ignore a severity or a confidence that is not one of the choices', async () => {
      const { fetchIncidents, find } = await open({
        route: '/incidents?severity=catastrophic&confidence=12&q[]=x',
      })

      expect(last(fetchIncidents)).toEqual({
        statuses: ['open', 'investigating'],
        verdicts: ['none', 'threat'],
        minConfidence: 0,
        limit: 25,
      })
      expect(find('clear-filters').exists()).toBe(false)
    })

    it('are all dropped by the button for it, but not the view', async () => {
      const { find, router, fetchIncidents, wrapper, choose } = await open({
        route: '/incidents?view=resolved&severity=high&confidence=65&q=source%3Awazuh',
      })

      await choose(() => find('clear-filters').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({ view: 'resolved' })
      expect(last(fetchIncidents)).toEqual({
        statuses: ['resolved'],
        verdicts: ['none', 'threat'],
        minConfidence: 0,
        limit: 25,
      })
      expect(wrapper.find<HTMLInputElement>('[data-test="search"] input').element.value).toBe('')
      expect(find('clear-filters').exists()).toBe(false)
    })
  })

  describe('the search', () => {
    const box = (wrapper: VueWrapper) =>
      wrapper.find<HTMLInputElement>('[data-test="search"] input')
    const term = (label: string, start: number, end: number, field: string | null = null) => ({
      field,
      label,
      negated: false,
      start,
      end,
    })
    /** Types something and presses Enter, which applies it at once. */
    const searchFor = async (wrapper: VueWrapper, text: string, choose: Choose) => {
      await box(wrapper).setValue(text)
      await choose(() => box(wrapper).trigger('keydown.enter'))
    }
    type Choose = (act: () => unknown) => Promise<void>
    interface Settle {
      resolve: (page: incidentsApi.IncidentPage) => void
      reject: (error: Error) => void
    }
    let pending: Settle

    it('starts empty and asks for no search', async () => {
      const { wrapper, fetchIncidents } = await open()

      expect(box(wrapper).element.value).toBe('')
      expect(last(fetchIncidents)).not.toHaveProperty('q')
    })

    it('asks for what was typed, with the time zone, and says so in the address of the page', async () => {
      const { wrapper, router, fetchIncidents, choose } = await open()

      await searchFor(wrapper, ' severity>=high  ssh ', choose)

      expect(last(fetchIncidents)).toMatchObject({
        q: 'severity>=high  ssh',
        tz: expect.any(String) as string,
      })
      expect(router.currentRoute.value.query).toEqual({ q: 'severity>=high  ssh' })
    })

    it('starts with the search that is in the address of the page', async () => {
      const { wrapper, fetchIncidents } = await open({ route: '/incidents?q=source%3Awazuh' })

      expect(box(wrapper).element.value).toBe('source:wazuh')
      expect(last(fetchIncidents).q).toBe('source:wazuh')
    })

    it('finds the address of a link from before the search had words', async () => {
      const { wrapper, router, fetchIncidents } = await open({
        route: '/incidents?view=all&address=93.184.216.34',
      })

      expect(box(wrapper).element.value).toBe('address:93.184.216.34')
      expect(last(fetchIncidents).q).toBe('address:93.184.216.34')
      // The address of the page is left as it was until something else is asked for.
      expect(router.currentRoute.value.query).toEqual({ view: 'all', address: '93.184.216.34' })
    })

    it('is one of the filters that the button clears', async () => {
      const { find, wrapper, router, choose } = await open()
      await searchFor(wrapper, 'ssh', choose)
      expect(find('clear-filters').exists()).toBe(true)

      await choose(() => find('clear-filters').trigger('click'))

      expect(box(wrapper).element.value).toBe('')
      expect(router.currentRoute.value.query).toEqual({})
    })

    it('shows how it was understood, a chip for each term, and a chip comes off with a tap', async () => {
      const { wrapper, router, fetchIncidents, choose } = await open({
        route: '/incidents?q=source%3Awazuh%20ssh',
        answer: page(some().items, {
          terms: [term('Source: Wazuh', 0, 12, 'source'), term('Contains: ssh', 13, 16)],
        }),
      })
      const chips = () => wrapper.findAll('[data-test="search-term"]').map((chip) => chip.text())
      expect(chips()).toEqual(['Source: Wazuh', 'Contains: ssh'])

      await choose(() => wrapper.find('[aria-label="Remove Source: Wazuh"]').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({ q: 'ssh' })
      expect(last(fetchIncidents).q).toBe('ssh')
      expect(box(wrapper).element.value).toBe('ssh')
    })

    it('says a search names a status, so it looks across every status', async () => {
      const { wrapper, router, fetchIncidents, choose } = await open()

      await searchFor(wrapper, 'status:resolved', choose)

      expect(router.currentRoute.value.query).toEqual({ view: 'all', q: 'status:resolved' })
      expect(last(fetchIncidents).statuses).toEqual([])
    })

    it('says a search names a verdict, so it includes the incidents your verdicts quiet', async () => {
      const { wrapper, router, fetchIncidents, choose } = await open()

      await searchFor(wrapper, 'verdict:not-suspicious', choose)

      expect(router.currentRoute.value.query).toEqual({
        q: 'verdict:not-suspicious',
        quieted: '1',
      })
      expect(last(fetchIncidents)).not.toHaveProperty('verdicts')
    })

    describe('that cannot be understood', () => {
      const refused = () =>
        new ApiError(422, 'There is no search field called "sevrity".', 'invalid')

      it('says why under the box and keeps what was listed, saying whose it is, with no chips', async () => {
        const { wrapper, find, fetchIncidents, choose, titles } = await open({
          route: '/incidents?q=ssh',
          answer: page(some().items, { terms: [term('Contains: ssh', 0, 3)] }),
        })
        expect(wrapper.findAll('[data-test="search-term"]')).toHaveLength(1)
        fetchIncidents.mockRejectedValue(refused())

        await searchFor(wrapper, 'sevrity:high', choose)

        expect(find('search').text()).toContain('There is no search field called "sevrity".')
        expect(find('search-stale').text()).toContain('last search that could be understood')
        expect(titles()).toHaveLength(2)
        expect(wrapper.findAll('[data-test="search-term"]')).toHaveLength(0)
        expect(find('incidents-error').exists()).toBe(false)
        expect(find('incidents-stale').exists()).toBe(false)
      })

      it('goes when the search is fixed', async () => {
        const { wrapper, find, fetchIncidents, choose } = await open()
        fetchIncidents.mockRejectedValueOnce(refused())
        await searchFor(wrapper, 'sevrity:high', choose)
        expect(find('search').text()).toContain('no search field')

        await searchFor(wrapper, 'severity:high', choose)

        expect(find('search').text()).not.toContain('no search field')
        expect(find('search-stale').exists()).toBe(false)
      })

      it('shows the page around it when it is the first thing asked, in a link', async () => {
        const fetchIncidents = vi.spyOn(incidentsApi, 'fetchIncidents')
        fetchIncidents.mockRejectedValueOnce(refused())
        fetchIncidents.mockResolvedValue(
          page([], { counts: { open: 0, investigating: 0, resolved: 4, dismissed: 0 }, total: 4 }),
        )
        const { wrapper } = await mountWithPlugins(IncidentsView, {
          signedIn: 'admin',
          withApp: true,
          route: '/incidents?q=sevrity%3Ahigh',
        })
        await flushPromises()

        expect(wrapper.find('[data-test="incidents-empty"]').text()).toContain(
          "That search can't be understood",
        )
        expect(wrapper.find('[data-test="count-all"]').text()).toBe('4')
        expect(wrapper.find('[data-test="more"]').exists()).toBe(false)
        expect(wrapper.find('[data-test="search"]').text()).toContain('no search field')
        expect((fetchIncidents.mock.calls[1]?.[0] as incidentsApi.IncidentQuery).q).toBeUndefined()
      })

      it('says so when even the page around it cannot be had', async () => {
        const fetchIncidents = vi.spyOn(incidentsApi, 'fetchIncidents')
        fetchIncidents.mockRejectedValueOnce(refused())
        fetchIncidents.mockRejectedValue(offline())
        const { wrapper } = await mountWithPlugins(IncidentsView, {
          signedIn: 'admin',
          withApp: true,
          route: '/incidents?q=sevrity%3Ahigh',
        })
        await flushPromises()

        expect(wrapper.find('[data-test="incidents-error"]').text()).toContain("Can't reach")
      })

      it.each([
        [
          'an answer',
          (settle: Settle) => {
            settle.resolve(page([], { total: 99 }))
          },
        ],
        [
          'a failure',
          (settle: Settle) => {
            settle.reject(offline())
          },
        ],
      ])(
        'drops %s about the page around it when something else was asked for since',
        async (_name, settle) => {
          const around = new Promise<incidentsApi.IncidentPage>((resolve, reject) => {
            pending = { resolve, reject }
          })
          const fetchIncidents = vi.spyOn(incidentsApi, 'fetchIncidents')
          fetchIncidents.mockRejectedValueOnce(refused())
          fetchIncidents.mockReturnValueOnce(around)
          fetchIncidents.mockResolvedValue(some())
          const { wrapper, router } = await mountWithPlugins(IncidentsView, {
            signedIn: 'admin',
            withApp: true,
            route: '/incidents?q=sevrity%3Ahigh',
          })
          await flushPromises()

          await router.replace({ query: { q: 'ssh' } })
          await flushPromises()
          settle(pending)
          await flushPromises()

          expect(wrapper.findAll('[data-test="incident-title"]')).toHaveLength(2)
          expect(wrapper.find('[data-test="incidents-error"]').exists()).toBe(false)
          expect(wrapper.find('[data-test="more"]').exists()).toBe(false)
        },
      )

      it('is not a search when it was something else the API refused', async () => {
        const { find } = await open({ answer: new ApiError(422, 'Nope.', 'invalid') })

        expect(find('incidents-error').text()).toContain('Nope.')
      })
    })

    describe('and what the results are made of', () => {
      it('adds a term for the severity or the integration that was chosen, and takes it out', async () => {
        const { find, router, fetchIncidents, choose } = await open()
        expect(find('facets').exists()).toBe(true)

        await choose(() => find('facet-severity:critical').trigger('click'))
        expect(router.currentRoute.value.query).toEqual({ q: 'severity:critical' })
        expect(last(fetchIncidents).q).toBe('severity:critical')
        expect(find('facet-severity:critical').attributes('aria-pressed')).toBe('true')

        await choose(() => find('facet-source:wazuh').trigger('click'))
        expect(router.currentRoute.value.query).toEqual({ q: 'severity:critical source:wazuh' })

        await choose(() => find('facet-severity:critical').trigger('click'))
        expect(router.currentRoute.value.query).toEqual({ q: 'source:wazuh' })
      })
    })

    describe('and the slash key', () => {
      const slash = (target: EventTarget = window, init: KeyboardEventInit = {}) => {
        const event = new KeyboardEvent('keydown', {
          key: '/',
          bubbles: true,
          cancelable: true,
          ...init,
        })
        target.dispatchEvent(event)
        return event
      }

      it('goes to the box from anywhere on the page', async () => {
        const { wrapper } = await open()
        const focus = vi.spyOn(box(wrapper).element, 'focus')

        expect(slash().defaultPrevented).toBe(true)

        expect(focus).toHaveBeenCalled()
      })

      it('is left alone in a field, and with Ctrl, Command or Alt', async () => {
        const { wrapper } = await open()
        const focus = vi.spyOn(box(wrapper).element, 'focus')

        expect(slash(box(wrapper).element).defaultPrevented).toBe(false)
        expect(slash(window, { ctrlKey: true }).defaultPrevented).toBe(false)
        expect(slash(window, { metaKey: true }).defaultPrevented).toBe(false)
        expect(slash(window, { altKey: true }).defaultPrevented).toBe(false)
        expect(slash(window, { key: 'k' }).defaultPrevented).toBe(false)

        expect(focus).not.toHaveBeenCalled()
      })

      it('stops when the page is left', async () => {
        const { wrapper } = await open()
        wrapper.unmount()

        expect(slash().defaultPrevented).toBe(false)
      })
    })
  })

  describe('the incidents your verdicts quiet', () => {
    const withQuieted = (count: number) => ({ answer: page(some().items, { quieted: count }) })

    it('are left out of the list, with no switch to show them when there are none', async () => {
      const { find } = await open()

      expect(find('filter-quieted').exists()).toBe(false)
    })

    it('are offered by a switch that says how many there are', async () => {
      const { text } = await open(withQuieted(4))

      expect(text('filter-quieted')).toBe('Show 4 quieted by your verdicts')
    })

    it('are listed once the switch is on, and say so in the address of the page', async () => {
      const { find, router, fetchIncidents, choose } = await open(withQuieted(4))

      await choose(() => find('filter-quieted').find('input').setValue(true))

      expect(router.currentRoute.value.query).toEqual({ quieted: '1' })
      expect(last(fetchIncidents)).toEqual({
        statuses: ['open', 'investigating'],
        minConfidence: 0,
        limit: 25,
      })
    })

    it('are left out again once it is switched off', async () => {
      const { find, router, fetchIncidents, choose } = await open({
        route: '/incidents?quieted=1',
        ...withQuieted(4),
      })
      expect(find('filter-quieted').find<HTMLInputElement>('input').element.checked).toBe(true)

      await choose(() => find('filter-quieted').find('input').setValue(false))

      expect(router.currentRoute.value.query).toEqual({})
      expect(last(fetchIncidents).verdicts).toEqual(['none', 'threat'])
    })

    it('count as a filter, which the button drops', async () => {
      const { find, router, choose } = await open({
        route: '/incidents?quieted=1',
        ...withQuieted(4),
      })

      await choose(() => find('clear-filters').trigger('click'))

      expect(router.currentRoute.value.query).toEqual({})
    })

    it('have no button to clear filters while nothing else is on', async () => {
      const { find } = await open(withQuieted(4))

      expect(find('clear-filters').exists()).toBe(false)
    })
  })

  describe('when there are no incidents to show', () => {
    const none = (counts = { open: 0, investigating: 0, resolved: 0, dismissed: 0 }) =>
      page([], { counts, total: 0 })

    it('says none have been made yet, and where the alerts come from', async () => {
      const { text, find } = await open({ answer: none() })

      expect(text('incidents-empty')).toContain('No incidents yet')
      expect(find('empty-integrations').attributes('href')).toBe('/integrations')
      expect(find('incident-list').exists()).toBe(false)
      expect(find('more').exists()).toBe(false)
    })

    it('says nothing needs anyone when the rest are over, and offers them', async () => {
      const { text, find, router, choose } = await open({
        answer: none({ open: 0, investigating: 0, resolved: 2, dismissed: 1 }),
      })

      expect(text('incidents-empty')).toContain('Nothing needs you')
      expect(text('incidents-empty')).toContain('3 in all')
      await choose(() => find('empty-all').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({ view: 'all' })
    })

    it('says every incident is one you quieted, and offers them', async () => {
      const { text, find, router, choose } = await open({
        answer: page([], {
          counts: { open: 0, investigating: 0, resolved: 0, dismissed: 0 },
          total: 0,
          quieted: 2,
        }),
      })

      expect(text('incidents-empty')).toContain('Nothing needs you')
      expect(text('incidents-empty')).toContain(
        'Every incident is one you called not suspicious or low priority. 2 are hidden.',
      )
      await choose(() => find('empty-quieted').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({ quieted: '1' })
    })

    it('says so in the singular for the one', async () => {
      const { text } = await open({
        answer: page([], {
          counts: { open: 0, investigating: 0, resolved: 0, dismissed: 0 },
          total: 0,
          quieted: 1,
        }),
      })

      expect(text('incidents-empty')).toContain('1 is hidden.')
    })

    it('says no incident has the status asked for', async () => {
      const { text } = await open({
        route: '/incidents?view=dismissed',
        answer: none({ open: 1, investigating: 0, resolved: 0, dismissed: 0 }),
      })

      expect(text('incidents-empty')).toContain('None here')
      expect(text('incidents-empty')).toContain('No incident has this status. 1 in all.')
    })

    it('says nothing matches the filters, and drops them', async () => {
      const { text, find, router, choose } = await open({
        route: '/incidents?severity=critical',
        answer: none({ open: 1, investigating: 0, resolved: 0, dismissed: 0 }),
      })

      expect(text('incidents-empty')).toContain('Nothing matches')
      await choose(() => find('empty-clear').trigger('click'))
      expect(router.currentRoute.value.query).toEqual({})
    })
  })

  describe('when there are more than one page of them', () => {
    const many = (from: number, count: number, total: number) =>
      page(
        Array.from({ length: count }, (_, index) =>
          incident({ id: from - index, title: `Incident ${from - index}` }),
        ),
        { total, counts: { open: total, investigating: 0, resolved: 0, dismissed: 0 } },
      )

    it('says how many are shown and offers the next page', async () => {
      const { text } = await open({ answer: many(100, 25, 60) })

      expect(text('more')).toContain('Showing 25 of 60.')
      expect(text('show-more')).toBe('Show 25 more')
    })

    it('adds the next page after the first, from where the first ended', async () => {
      const { find, text, titles, fetchIncidents, choose } = await open({
        answer: many(100, 25, 60),
      })
      fetchIncidents.mockResolvedValue(many(75, 25, 60))

      await choose(() => find('show-more').trigger('click'))

      expect(last(fetchIncidents)).toMatchObject({ offset: 25, limit: 25 })
      expect(titles()).toHaveLength(50)
      expect(titles()[25]).toBe('Incident 75')
      expect(text('more')).toContain('Showing 50 of 60.')
      expect(text('show-more')).toBe('Show 10 more')
    })

    it('stops offering more when all are shown', async () => {
      const { find, fetchIncidents, choose } = await open({ answer: many(100, 25, 30) })
      fetchIncidents.mockResolvedValue(many(75, 5, 30))

      await choose(() => find('show-more').trigger('click'))

      expect(find('more').exists()).toBe(false)
    })

    it('keeps as many as are on screen when it asks again, so nothing disappears', async () => {
      const { find, fetchIncidents, choose } = await open({ answer: many(100, 25, 60) })
      fetchIncidents.mockResolvedValue(many(75, 25, 60))
      await choose(() => find('show-more').trigger('click'))

      fetchIncidents.mockResolvedValue(many(100, 50, 60))
      await choose(() => find('refresh').trigger('click'))

      expect(last(fetchIncidents).limit).toBe(50)
      expect(last(fetchIncidents).offset).toBeUndefined()
    })

    it('says so when the next page cannot be had, and keeps the first', async () => {
      const { find, text, titles, fetchIncidents, choose } = await open({
        answer: many(100, 25, 60),
      })
      fetchIncidents.mockRejectedValue(offline())

      await choose(() => find('show-more').trigger('click'))

      expect(text('incidents-stale')).toContain("Can't reach AresGate.")
      expect(titles()).toHaveLength(25)
    })

    it('drops the answer for a page that is no longer wanted', async () => {
      const { find, titles, fetchIncidents, choose } = await open({ answer: many(100, 25, 60) })
      let late: (value: incidentsApi.IncidentPage) => void = () => {}
      fetchIncidents.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      await choose(() => find('show-more').trigger('click'))
      fetchIncidents.mockResolvedValueOnce(many(100, 25, 60))
      await choose(() => find('refresh').trigger('click'))

      late(many(75, 25, 60))
      await flushPromises()

      expect(titles()).toHaveLength(25)
    })

    it('drops the failure of a page that is no longer wanted', async () => {
      const { find, fetchIncidents, choose } = await open({ answer: many(100, 25, 60) })
      let fail: (reason: Error) => void = () => {}
      fetchIncidents.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      await choose(() => find('show-more').trigger('click'))
      fetchIncidents.mockResolvedValueOnce(many(100, 25, 60))
      await choose(() => find('refresh').trigger('click'))

      fail(offline())
      await flushPromises()

      expect(find('incidents-stale').exists()).toBe(false)
    })
  })

  describe('refreshing', () => {
    it('asks again when told to', async () => {
      const { find, fetchIncidents, choose } = await open()

      await choose(() => find('refresh').trigger('click'))

      expect(fetchIncidents).toHaveBeenCalledTimes(2)
    })

    it('asks again every half minute while the page is open, leaving what is on screen alone', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { fetchIncidents, find } = await open()
        fetchIncidents.mockReturnValue(new Promise(() => {}))

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(fetchIncidents).toHaveBeenCalledTimes(2)
        expect(find('incident-list').exists()).toBe(true)
        expect(find('incidents-loading').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    it('ignores the answer to a choice that is no longer the one made', async () => {
      const { find, titles, fetchIncidents, choose } = await open()
      let late: (value: incidentsApi.IncidentPage) => void = () => {}
      fetchIncidents.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
      await choose(() => find('view-resolved').trigger('click'))
      fetchIncidents.mockResolvedValueOnce(page([incident({ id: 8, title: 'The other one' })]))
      await choose(() => find('view-all').trigger('click'))

      late(page([incident({ id: 9, title: 'Too late' })]))
      await flushPromises()

      expect(titles()).toEqual(['The other one'])
    })

    it('ignores the failure of a choice that is no longer the one made', async () => {
      const { find, fetchIncidents, choose } = await open()
      let fail: (reason: Error) => void = () => {}
      fetchIncidents.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      await choose(() => find('view-resolved').trigger('click'))
      await choose(() => find('view-all').trigger('click'))

      fail(offline())
      await flushPromises()

      expect(find('incidents-stale').exists()).toBe(false)
    })
  })

  describe('when it cannot be loaded', () => {
    it('says so, and tries again', async () => {
      const { find, text, fetchIncidents, choose } = await open({ answer: offline() })

      expect(text('incidents-error')).toContain("Can't reach AresGate.")
      expect(find('incident-list').exists()).toBe(false)

      fetchIncidents.mockResolvedValue(some())
      await choose(() => find('retry').trigger('click'))

      expect(find('incidents-error').exists()).toBe(false)
      expect(find('incident-list').exists()).toBe(true)
    })

    it('keeps what it has while a refresh fails, and says how old it is', async () => {
      const { find, text, titles, fetchIncidents, choose } = await open()
      fetchIncidents.mockRejectedValue(offline())

      await choose(() => find('refresh').trigger('click'))

      expect(text('incidents-stale')).toContain("Can't reach AresGate.")
      expect(text('incidents-stale')).toMatch(/is from \d/)
      expect(titles()).toHaveLength(2)

      fetchIncidents.mockResolvedValue(some())
      await choose(() => find('refresh').trigger('click'))
      expect(find('incidents-stale').exists()).toBe(false)
    })

    it('goes to the sign-in page when the sign-in has ended', async () => {
      const { pinia } = await open({
        answer: new ApiError(401, 'Sign in.', 'unauthenticated') as unknown as Error,
      })

      expect(useSessionStore(pinia).expired).toBe(true)
    })
  })
  describe('saying what you think of an incident from the list', () => {
    /** What the page says in its notice at the bottom, which is outside the page itself. */
    const notice = (selector: string) =>
      document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

    async function judge(kept = given()) {
      const give = vi.spyOn(verdictsApi, 'giveVerdict').mockResolvedValue(kept)
      const change = vi.spyOn(verdictsApi, 'changeVerdict').mockResolvedValue(kept)
      const remove = vi.spyOn(verdictsApi, 'removeVerdict').mockResolvedValue(undefined)
      const opened = await open()
      const press = async (kind: string) => {
        await opened.wrapper.find(`[data-test="quick-${kind}"]`).trigger('click')
        await flushPromises()
        await flushPromises()
      }
      const undo = async () => {
        notice('undo')?.click()
        await flushPromises()
        await flushPromises()
      }
      return { ...opened, give, change, remove, press, undo }
    }

    it('says what was remembered and asks for the list again, since it can leave it', async () => {
      const { press, fetchIncidents } = await judge()

      await press('not_suspicious')

      expect(notice('judged-text')?.textContent).toBe(
        'Remembered: 93.184.216.34 is not suspicious.',
      )
      expect(fetchIncidents).toHaveBeenCalledTimes(2)
    })

    it('takes back a new verdict, and asks for the list again', async () => {
      const { press, undo, remove, change, fetchIncidents } = await judge(given({ id: 7 }))
      await press('not_suspicious')

      await undo()

      expect(remove).toHaveBeenCalledWith(7, 'a-security-token')
      expect(change).not.toHaveBeenCalled()
      expect(notice('judged-text')?.textContent).toBe('Taken back.')
      expect(notice('undo')).toBeNull()
      expect(fetchIncidents).toHaveBeenCalledTimes(3)
    })
  })
})
